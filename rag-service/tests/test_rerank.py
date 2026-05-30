"""Unit tests for rag_service.rerank.

Layer-1 tests (pure, no FastAPI involved) plus a live-model test that
auto-skips when the real bge-reranker-v2-m3 weights aren't on disk. Same
shape as test_embed.py — see that file's docstring for the rationale.
"""

from __future__ import annotations

import os

import pytest

from rag_service import rerank
from rag_service.rerank import MODEL_PATH, Reranker, get_reranker


# ---------------------------------------------------------------------------
# Module-level config
# ---------------------------------------------------------------------------


def test_model_path_defaults_to_baked_in_container_path():
    if "RAG_SERVICE_BGE_RERANKER_PATH" in os.environ:
        pytest.skip(
            "RAG_SERVICE_BGE_RERANKER_PATH set; default-path test not applicable"
        )
    assert MODEL_PATH == "/models/bge-reranker-v2-m3"


# ---------------------------------------------------------------------------
# max_length cap (BILL-37): the cross-encoder MUST be constructed with a
# max_length, or scoring long ticket chunks is O(seq^2) — measured ~770s/~25GB
# uncapped vs ~28s/~3.3GB at 512. Reranker.__init__ lazy-imports
# `from sentence_transformers import CrossEncoder`, so we inject a fake
# sentence_transformers module into sys.modules and capture the kwargs.
# ---------------------------------------------------------------------------


def _capture_crossencoder_kwargs(monkeypatch):
    """Install a fake `sentence_transformers.CrossEncoder` and return a dict
    that records the kwargs it was constructed with."""
    import sys
    import types

    captured: dict = {}

    class _FakeCrossEncoder:
        def __init__(self, model_path, **kwargs):
            captured["model_path"] = model_path
            captured["kwargs"] = kwargs

    fake_mod = types.ModuleType("sentence_transformers")
    fake_mod.CrossEncoder = _FakeCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
    return captured


def test_reranker_caps_max_length_by_default(monkeypatch):
    from rag_service.rerank import MAX_LENGTH

    captured = _capture_crossencoder_kwargs(monkeypatch)
    Reranker(model_path="/fake/path")
    # Reranker must pass the module-level cap through to the CrossEncoder.
    # Assert against MAX_LENGTH (not a literal) so this stays correct when
    # RAG_SERVICE_RERANKER_MAX_LENGTH is set in the environment.
    assert captured["kwargs"].get("max_length") == MAX_LENGTH
    # The documented default is 512; only check it when no override is active,
    # same skip pattern as test_model_path_defaults_to_baked_in_container_path.
    if "RAG_SERVICE_RERANKER_MAX_LENGTH" not in os.environ:
        assert MAX_LENGTH == 512


def test_reranker_max_length_override(monkeypatch):
    captured = _capture_crossencoder_kwargs(monkeypatch)
    Reranker(model_path="/fake/path", max_length=128)
    assert captured["kwargs"].get("max_length") == 128


@pytest.mark.parametrize("bad", ["0", "-1", "notanint", ""])
def test_parse_max_length_rejects_non_positive_and_non_int(bad):
    """A non-positive or non-integer cap is a misconfiguration; _parse_max_length
    must raise ValueError at parse time rather than letting it reach the model."""
    with pytest.raises(ValueError):
        rerank._parse_max_length(bad)


def test_parse_max_length_accepts_positive():
    assert rerank._parse_max_length("256") == 256


# ---------------------------------------------------------------------------
# Empty-passages short-circuit
# ---------------------------------------------------------------------------


def test_score_returns_empty_list_for_empty_passages():
    """score([]) must return [] WITHOUT touching the underlying model — the
    real CrossEncoder.predict raises on an empty input. We bypass __init__
    via object.__new__ so this test doesn't need the real model on disk.
    """
    r = object.__new__(Reranker)
    # Trip-wire: if score forgets the short-circuit and calls into _model,
    # this attribute makes the failure mode loud and obvious instead of
    # AttributeError several frames deep.
    r._model = None
    assert r.score("anything", []) == []


# ---------------------------------------------------------------------------
# Provider singleton
# ---------------------------------------------------------------------------


def test_get_reranker_returns_cached_singleton(monkeypatch):
    monkeypatch.setattr(rerank, "_reranker", None)

    construct_count = {"n": 0}

    class _Counting:
        def __init__(self):
            construct_count["n"] += 1

    monkeypatch.setattr(rerank, "Reranker", _Counting)

    a = get_reranker()
    b = get_reranker()
    assert a is b
    assert construct_count["n"] == 1


# ---------------------------------------------------------------------------
# Live model — auto-skip when weights absent
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.path.isdir(MODEL_PATH),
    reason=f"bge-reranker-v2-m3 weights not present at {MODEL_PATH}; live model "
    "test only runs inside the rag image (verify-bill17.sh covers it).",
)
def test_score_returns_float_per_passage_in_input_order():
    r = Reranker()
    query = "scheduler dispatch loop"
    passages = [
        "the scheduler dispatches jobs every N seconds",
        "unrelated content about authentication flows",
        "more scheduler internals: queue draining",
    ]
    scores = r.score(query, passages)
    assert len(scores) == len(passages)
    assert all(isinstance(s, float) for s in scores)
