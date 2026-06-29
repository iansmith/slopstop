"""SCIP code-graph harvester — detect repo languages, invoke SCIP indexers, POST to /code-graph/ingest."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from rag_service.harvesters._common import read_project_conf

_ALWAYS_SKIP: frozenset[str] = frozenset({"vendor", ".git", "node_modules", "__pycache__"})

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
}

_TOOL_FOR_LANG: dict[str, str] = {
    "python": "scip-python",
    "go": "scip-go",
    "typescript": "scip-typescript",
}

_INSTALL_MSG: dict[str, str] = {
    "scip-python": "pip install scip-python",
    "scip-go": "go install github.com/sourcegraph/scip-go/cmd/scip-go@latest",
    "scip-typescript": "npm install -g @sourcegraph/scip-typescript",
    "scip": "go install github.com/sourcegraph/scip/cmd/scip@latest",
}


class PreflightError(RuntimeError):
    pass


def detect_languages(repo_dir: Path, skip: list[str]) -> list[str]:
    """Walk repo_dir and return sorted list of detected language names."""
    skip_names = _ALWAYS_SKIP | {s.rstrip("/") for s in skip}
    all_langs = set(_TOOL_FOR_LANG)
    langs: set[str] = set()
    for _, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in skip_names]
        for fname in filenames:
            lang = _EXT_TO_LANG.get(os.path.splitext(fname)[1])
            if lang:
                langs.add(lang)
        if langs >= all_langs:
            break
    return sorted(langs)


def check_preflight(languages: list[str]) -> None:
    """Verify required SCIP tools are on PATH; raise PreflightError listing missing ones."""
    if not languages:
        return
    tools_needed = {"scip"}
    for lang in languages:
        tool = _TOOL_FOR_LANG.get(lang)
        if not tool:
            raise PreflightError(
                f"Unsupported language: {lang!r}. Supported: {sorted(_TOOL_FOR_LANG)}"
            )
        tools_needed.add(tool)
    missing = [t for t in sorted(tools_needed) if shutil.which(t) is None]
    if missing:
        lines = ["Missing SCIP tools. Install with:"]
        for tool in missing:
            lines.append(f"  {tool}: {_INSTALL_MSG.get(tool, 'see SCIP documentation')}")
        raise PreflightError("\n".join(lines))


def build_ingest_payload(
    index: dict,
    repo: str,
    head_sha: str | None,
    source_root: str | None,
) -> dict:
    """Build the JSON body for POST /code-graph/ingest."""
    return {"repo": repo, "index": index, "head_sha": head_sha, "source_root": source_root}


def run_scip_indexer(lang: str, repo_dir: Path, module_root: str | None) -> dict:
    """Run the SCIP indexer for lang inside a temp dir; return the parsed JSON index."""
    if module_root and Path(module_root).is_absolute():
        raise ValueError(f"module_root must be a relative path, got: {module_root!r}")
    work_dir = (Path(repo_dir) / module_root).resolve() if module_root else Path(repo_dir).resolve()

    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "index.scip"
        run_cwd = None

        if lang == "python":
            cmd = ["scip-python", "index", "--cwd", str(work_dir), "--output", str(index_path), "--quiet"]
        elif lang == "go":
            cmd = ["scip-go", ".", "--output", str(index_path)]
            run_cwd = str(work_dir)
        elif lang == "typescript":
            cmd = ["scip-typescript", "index", "--project-root", str(work_dir), "--output", str(index_path)]
        else:
            raise ValueError(f"Unsupported language: {lang}")

        result = subprocess.run(cmd, cwd=run_cwd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"scip-{lang} failed:\n{result.stderr}")
        if not index_path.exists():
            raise RuntimeError(f"scip-{lang} exited 0 but wrote no index file at {index_path}")

        print_result = subprocess.run(
            ["scip", "print", "--json", str(index_path)],
            capture_output=True,
            text=True,
        )
        if print_result.returncode != 0:
            raise RuntimeError(f"scip print failed:\n{print_result.stderr}")

        return json.loads(print_result.stdout)


def post_ingest(payload: dict, rag_url: str) -> dict:
    """POST payload to /code-graph/ingest; raise on non-2xx; return response JSON."""
    import httpx

    resp = httpx.post(f"{rag_url}/code-graph/ingest", json=payload, timeout=300.0)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(
            f"/code-graph/ingest returned non-JSON body: {resp.text[:200]!r}"
        ) from exc


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m rag_service.harvesters.scip",
        description="SCIP code-graph harvester",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    idx = sub.add_parser("index", help="Index a repo into the code graph.")
    idx.add_argument("repo_dir", help="Path to the repo root.")
    idx.add_argument("project", help="Project name (e.g. 'iansmith/slopstop').")
    idx.add_argument(
        "--rag-url",
        default=os.environ.get("RAG_SERVICE_URL", "http://localhost:7777"),
        help="RAG service base URL.",
    )
    idx.add_argument(
        "--module-root",
        default=None,
        help="Override [code-graph] module_root from .project-conf.toml.",
    )

    return p


def _cmd_index(args: argparse.Namespace) -> None:
    repo_dir = Path(args.repo_dir).expanduser().resolve()
    if not repo_dir.is_dir():
        sys.exit(f"Not a directory: {repo_dir}")

    cg_conf = read_project_conf(str(repo_dir)).get("code-graph", {})
    module_root = args.module_root or cg_conf.get("module_root") or ""
    if module_root and Path(module_root).is_absolute():
        sys.exit(f"module_root must be a relative path, got: {module_root!r}")
    skip = cg_conf.get("skip", [])
    configured = cg_conf.get("languages")
    languages = configured if configured is not None else detect_languages(repo_dir, skip)

    if not languages:
        print("No supported languages detected.", file=sys.stderr)
        return

    try:
        check_preflight(languages)
    except PreflightError as e:
        sys.exit(str(e))

    try:
        head_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_dir),
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        head_sha = None

    source_root = str(repo_dir / module_root)

    print(f"Indexing {len(languages)} language(s) from {repo_dir} (project={args.project})")
    for lang in languages:
        print(f"  [{lang}] running scip indexer...")
        index = run_scip_indexer(lang, repo_dir, module_root)
        payload = build_ingest_payload(
            index=index,
            repo=args.project,
            head_sha=head_sha,
            source_root=source_root,
        )
        result = post_ingest(payload, args.rag_url)
        print(f"  [{lang}] {result.get('vertices_merged', '?')} vertices, {result.get('edges_merged', '?')} edges")

    print("Done.")


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    _cmd_index(args)


if __name__ == "__main__":
    main()
