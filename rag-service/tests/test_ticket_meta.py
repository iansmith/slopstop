"""Phase 0 red tests for BILL-51 — ticket_meta table + structured filters.

These tests describe the expected post-implementation behavior.
They FAIL on current code because the fields / table / JOIN logic
don't exist yet. They turn green as each work item is completed.

Layer split (design/rag-service-testing.md):
  - Layer 1: pure dataclass / model instantiation (no FastAPI, no postgres)
  - Layer 2: TestClient + dependency_overrides (no real postgres)
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Layer 1 — HarvestedTicket metadata fields
# ---------------------------------------------------------------------------


def test_harvested_ticket_has_state_norm_field():
    """HarvestedTicket must accept state_norm and state_name."""
    from rag_service.harvesters._common import HarvestedTicket

    t = HarvestedTicket(
        source="linear",
        ticket_id="LOU-1",
        title="Test ticket",
        description="desc",
        state_norm="in_progress",
        state_name="In Progress",
    )
    assert t.state_norm == "in_progress"
    assert t.state_name == "In Progress"


def test_harvested_ticket_has_people_fields():
    """HarvestedTicket must accept assignee and reporter."""
    from rag_service.harvesters._common import HarvestedTicket

    t = HarvestedTicket(
        source="linear",
        ticket_id="LOU-2",
        title="Test",
        description="desc",
        assignee="Ian Smith",
        reporter="Ian Smith",
    )
    assert t.assignee == "Ian Smith"
    assert t.reporter == "Ian Smith"


def test_harvested_ticket_has_priority_fields():
    """HarvestedTicket must accept priority_num (0–4 int) and priority_name."""
    from rag_service.harvesters._common import HarvestedTicket

    t = HarvestedTicket(
        source="linear",
        ticket_id="LOU-3",
        title="Test",
        description="desc",
        priority_num=2,
        priority_name="High",
    )
    assert t.priority_num == 2
    assert t.priority_name == "High"


def test_harvested_ticket_has_classification_fields():
    """HarvestedTicket must accept issue_type, ticket_labels, milestone."""
    from rag_service.harvesters._common import HarvestedTicket

    t = HarvestedTicket(
        source="linear",
        ticket_id="LOU-4",
        title="Test",
        description="desc",
        issue_type="bug",
        ticket_labels=["regression", "P1"],
        milestone="Phase 22",
    )
    assert t.issue_type == "bug"
    assert t.ticket_labels == ["regression", "P1"]
    assert t.milestone == "Phase 22"


def test_harvested_ticket_has_timing_fields():
    """HarvestedTicket must accept ticket_created_at, ticket_updated_at,
    ticket_closed_at as datetime | None."""
    from rag_service.harvesters._common import HarvestedTicket

    now = datetime.now(tz=timezone.utc)
    t = HarvestedTicket(
        source="linear",
        ticket_id="LOU-5",
        title="Test",
        description="desc",
        ticket_created_at=now,
        ticket_updated_at=now,
        ticket_closed_at=None,
    )
    assert t.ticket_created_at == now
    assert t.ticket_updated_at == now
    assert t.ticket_closed_at is None


def test_harvested_ticket_metadata_fields_default_to_none():
    """All new metadata fields must have None/[] defaults so existing
    harvester callsites that don't set them don't break."""
    from rag_service.harvesters._common import HarvestedTicket

    t = HarvestedTicket(
        source="linear", ticket_id="LOU-6", title="t", description="d"
    )
    assert t.state_norm is None
    assert t.state_name is None
    assert t.assignee is None
    assert t.reporter is None
    assert t.priority_num is None
    assert t.priority_name is None
    assert t.issue_type is None
    assert t.ticket_labels == []
    assert t.milestone is None
    assert t.ticket_created_at is None
    assert t.ticket_updated_at is None
    assert t.ticket_closed_at is None


# ---------------------------------------------------------------------------
# Layer 1 — SearchFilters metadata fields
# ---------------------------------------------------------------------------


def test_search_filters_has_assignee_field():
    """SearchFilters must accept an assignee string filter."""
    from rag_service.models import SearchFilters

    f = SearchFilters(assignee="Ian Smith")
    assert f.assignee == "Ian Smith"


def test_search_filters_has_state_norm_field():
    """SearchFilters must accept a state_norm filter."""
    from rag_service.models import SearchFilters

    f = SearchFilters(state_norm="open")
    assert f.state_norm == "open"

    f2 = SearchFilters(state_norm="in_progress")
    assert f2.state_norm == "in_progress"


def test_search_filters_has_priority_max_field():
    """SearchFilters must accept priority_max (int 0–4): include tickets
    with priority_num <= priority_max."""
    from rag_service.models import SearchFilters

    f = SearchFilters(priority_max=2)
    assert f.priority_max == 2


def test_search_filters_has_labels_field():
    """SearchFilters must accept a labels list for any-of matching."""
    from rag_service.models import SearchFilters

    f = SearchFilters(labels=["bug", "P1"])
    assert f.labels == ["bug", "P1"]


def test_search_filters_has_date_fields():
    """SearchFilters must accept created_after and updated_after as ISO date
    strings (parsed to date objects by Pydantic) or date objects directly."""
    from rag_service.models import SearchFilters

    f = SearchFilters(created_after="2025-01-01", updated_after="2025-06-01")
    assert f.created_after == date(2025, 1, 1)
    assert f.updated_after == date(2025, 6, 1)


def test_search_filters_rejects_invalid_state_norm():
    """state_norm must be restricted to the four documented values;
    an arbitrary string must raise a Pydantic ValidationError."""
    from pydantic import ValidationError

    from rag_service.models import SearchFilters

    with pytest.raises(ValidationError):
        SearchFilters(state_norm="in_review")  # not in the allowed Literal set


def test_search_filters_rejects_out_of_range_priority_max():
    """priority_max must be 0–4; values outside that range must raise a
    ValidationError rather than silently flowing into the SQL."""
    from pydantic import ValidationError

    from rag_service.models import SearchFilters

    with pytest.raises(ValidationError):
        SearchFilters(priority_max=5)
    with pytest.raises(ValidationError):
        SearchFilters(priority_max=-1)


def test_search_filters_normalizes_empty_labels_to_none():
    """labels=[] must be coerced to None so the meta JOIN is not triggered
    with a match-nothing empty array."""
    from rag_service.models import SearchFilters

    f = SearchFilters(labels=[])
    assert f.labels is None  # normalized by the field_validator


def test_search_filters_new_fields_default_to_none():
    """All new filter fields must default to None so existing callers
    that construct SearchFilters() without them are unaffected."""
    from rag_service.models import SearchFilters

    f = SearchFilters()
    assert f.assignee is None
    assert f.state_norm is None
    assert f.priority_max is None
    assert f.labels is None
    assert f.created_after is None
    assert f.updated_after is None


# ---------------------------------------------------------------------------
# Layer 2 — filter propagation through the search endpoint
# ---------------------------------------------------------------------------


def test_search_endpoint_passes_assignee_to_knn_search(client, fake_db):
    """POST /search with filters.assignee='Ian Smith' must pass assignee
    through to knn_search — the DB layer must receive the filter."""
    received: list = []

    original_knn = fake_db.knn_search

    def recording_knn(vec, k, filters=None):
        received.append(filters)
        return original_knn(vec, k, filters)

    fake_db.knn_search = recording_knn
    fake_db.chunks = []

    r = client.post(
        "/search",
        json={"query": "tree", "filters": {"assignee": "Ian Smith"}},
    )
    assert r.status_code == 200
    assert len(received) == 1
    assert received[0] is not None
    assert received[0].assignee == "Ian Smith"


def test_search_endpoint_passes_state_norm_to_knn_search(client, fake_db):
    """POST /search with filters.state_norm='open' must pass state_norm
    through to knn_search."""
    received: list = []

    def recording_knn(vec, k, filters=None):
        received.append(filters)
        return []

    fake_db.knn_search = recording_knn

    r = client.post(
        "/search",
        json={"query": "overflow", "filters": {"state_norm": "open"}},
    )
    assert r.status_code == 200
    assert received[0].state_norm == "open"


def test_search_endpoint_passes_labels_filter_to_knn_search(client, fake_db):
    """POST /search with filters.labels=['bug'] must pass labels through."""
    received: list = []

    def recording_knn(vec, k, filters=None):
        received.append(filters)
        return []

    fake_db.knn_search = recording_knn

    r = client.post(
        "/search",
        json={"query": "border", "filters": {"labels": ["bug"]}},
    )
    assert r.status_code == 200
    assert received[0].labels == ["bug"]


# ---------------------------------------------------------------------------
# Layer 1 — _build_knn_sql JOIN logic (BILL-51)
# ---------------------------------------------------------------------------


def test_build_knn_sql_no_meta_filters_has_no_join():
    """When no metadata filters are set, query must NOT include a JOIN
    (performance: avoid join overhead for normal searches)."""
    from rag_service.db import _build_knn_sql
    from rag_service.models import SearchFilters

    sql, _ = _build_knn_sql([0.0] * 1024, k=10, filters=SearchFilters())
    assert "JOIN" not in sql.upper()
    assert "ticket_meta" not in sql


def test_build_knn_sql_assignee_filter_adds_join_and_where():
    """When assignee filter is set, query must INNER JOIN ticket_meta and
    filter by assignee ILIKE."""
    from rag_service.db import _build_knn_sql
    from rag_service.models import SearchFilters

    sql, params = _build_knn_sql(
        [0.0] * 1024, k=10, filters=SearchFilters(assignee="Ian Smith")
    )
    assert "INNER JOIN" in sql.upper()
    assert "ticket_meta" in sql
    assert "ILIKE" in sql.upper()
    assert "Ian Smith" in params


def test_build_knn_sql_state_norm_filter_adds_where():
    from rag_service.db import _build_knn_sql
    from rag_service.models import SearchFilters

    sql, params = _build_knn_sql(
        [0.0] * 1024, k=10, filters=SearchFilters(state_norm="open")
    )
    assert "state_norm" in sql
    assert "open" in params


def test_build_knn_sql_labels_filter_uses_array_overlap():
    """labels filter must use the && (array overlap) operator."""
    from rag_service.db import _build_knn_sql
    from rag_service.models import SearchFilters

    sql, params = _build_knn_sql(
        [0.0] * 1024, k=10, filters=SearchFilters(labels=["bug", "P1"])
    )
    assert "&&" in sql
    assert ["bug", "P1"] in params


def test_build_knn_sql_priority_max_filter_adds_lte_where():
    """priority_max filter must produce a <= WHERE clause against
    ticket_meta.priority_num."""
    from rag_service.db import _build_knn_sql
    from rag_service.models import SearchFilters

    sql, params = _build_knn_sql(
        [0.0] * 1024, k=10, filters=SearchFilters(priority_max=2)
    )
    assert "priority_num" in sql
    assert "<=" in sql
    assert 2 in params


def test_build_knn_sql_date_filters_add_gte_where():
    """created_after and updated_after filters must produce >= WHERE clauses
    against the corresponding ticket_meta timestamp columns."""
    from rag_service.db import _build_knn_sql
    from rag_service.models import SearchFilters

    f = SearchFilters(created_after="2025-01-01", updated_after="2025-06-01")
    sql, params = _build_knn_sql([0.0] * 1024, k=10, filters=f)
    assert "ticket_created_at" in sql
    assert "ticket_updated_at" in sql
    assert ">=" in sql
    assert date(2025, 1, 1) in params
    assert date(2025, 6, 1) in params


# ---------------------------------------------------------------------------
# Layer 2 — endpoint propagation for priority_max, created_after, updated_after
# ---------------------------------------------------------------------------


def test_search_endpoint_passes_priority_max_to_knn_search(client, fake_db):
    """POST /search with filters.priority_max=2 must pass priority_max
    through to knn_search."""
    received: list = []

    def recording_knn(vec, k, filters=None):
        received.append(filters)
        return []

    fake_db.knn_search = recording_knn

    r = client.post(
        "/search",
        json={"query": "overflow", "filters": {"priority_max": 2}},
    )
    assert r.status_code == 200
    assert received[0].priority_max == 2


def test_search_endpoint_passes_created_after_to_knn_search(client, fake_db):
    """POST /search with filters.created_after='2025-01-01' must pass
    created_after (as a date object) through to knn_search."""
    received: list = []

    def recording_knn(vec, k, filters=None):
        received.append(filters)
        return []

    fake_db.knn_search = recording_knn

    r = client.post(
        "/search",
        json={"query": "multicol", "filters": {"created_after": "2025-01-01"}},
    )
    assert r.status_code == 200
    assert received[0].created_after == date(2025, 1, 1)


def test_search_endpoint_passes_updated_after_to_knn_search(client, fake_db):
    """POST /search with filters.updated_after='2025-06-01' must pass
    updated_after (as a date object) through to knn_search."""
    received: list = []

    def recording_knn(vec, k, filters=None):
        received.append(filters)
        return []

    fake_db.knn_search = recording_knn

    r = client.post(
        "/search",
        json={"query": "paint", "filters": {"updated_after": "2025-06-01"}},
    )
    assert r.status_code == 200
    assert received[0].updated_after == date(2025, 6, 1)
