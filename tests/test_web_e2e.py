"""End-to-end web tests via FastAPI TestClient.

Covers cross-cutting route behaviour that unit tests miss: auth gating, the
run-detail page rendering for every run status (regression for the B1 500), and a
"bad id ⇒ 404 not 500" sweep. Runs in-process against an isolated data dir
(see conftest.py); BackgroundTasks execute synchronously under TestClient.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from fcmr_core.catalog import store


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        # Authenticate (admin/admin123 is seeded on startup).
        r = c.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=True,
        )
        assert r.status_code == 200, "login failed"
        yield c


def _make_run(status: str, error: str | None = None) -> str:
    eid = store.create_engagement(name="WebTest Eng", client_name="Client")
    upload_id = store.create_upload(
        report_type="customer_master", filename="webtest.csv", engagement_id=eid
    )
    run_id = store.create_run(upload_id=upload_id, engagement_id=eid)
    kwargs: dict[str, str | None] = {"status": status}
    if error is not None:
        kwargs["error"] = error
    store.update_run(run_id, **kwargs)
    return run_id


def test_failed_run_detail_renders_200_with_error(client):
    """Regression for B1: a failed run's detail page must render (was a 500)."""
    run_id = _make_run("failed", error="Boom: synthetic failure for test")
    r = client.get(f"/runs/{run_id}")
    assert r.status_code == 200, r.text[:500]
    assert "Boom: synthetic failure for test" in r.text


@pytest.mark.parametrize("status", ["pending", "running", "cancelled"])
def test_nonterminal_run_detail_renders_200(client, status):
    """Pending/running/cancelled run detail pages must also render (B1)."""
    run_id = _make_run(status)
    r = client.get(f"/runs/{run_id}")
    assert r.status_code == 200, r.text[:500]


def test_bad_login_shows_inline_error_not_raw_401(client):
    """B6: invalid credentials re-render login.html with an inline error (401)."""
    r = client.post(
        "/login",
        data={"username": "admin", "password": "wrong-password"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "Invalid username or password" in r.text
    # Must be the rendered HTML login page, not a bare JSON 401.
    assert "<form" in r.text and "SanGir Automations" in r.text


def _staged_upload(headers: list[str], rows: list[str]) -> str:
    """Create a mapping-pending upload backed by a CSV on disk."""
    import tempfile
    from pathlib import Path

    eid = store.create_engagement(name="Upload Test")
    upload_id = store.create_upload(
        report_type="customer_master", filename="u.csv", engagement_id=eid
    )
    td = Path(tempfile.mkdtemp(prefix="fcmr_upl_"))
    csv_path = td / "u.csv"
    csv_path.write_text("\n".join([",".join(headers), *rows]) + "\n")
    store.set_mapping_pending(upload_id, csv_path=csv_path, sniffed_headers=headers)
    return upload_id


def test_duplicate_column_mapping_rejected(client):
    """B4: mapping two canonical fields to the same source column => 400."""
    upload_id = _staged_upload(["A", "B"], ["1,2"])
    r = client.post(
        f"/dashboard/uploads/{upload_id}/map-columns",
        data={"map_customer_id": "A", "map_full_name": "A", "map_lan": "B"},
        follow_redirects=False,
    )
    assert r.status_code == 400, r.text[:300]


def test_empty_csv_upload_marked_failed(client):
    """B5: a header-only CSV must end 'failed', not 'ready'."""
    upload_id = _staged_upload(["customer_id", "full_name", "lan"], [])
    r = client.post(
        f"/dashboard/uploads/{upload_id}/map-columns",
        data={
            "map_customer_id": "customer_id",
            "map_full_name": "full_name",
            "map_lan": "lan",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400, r.text[:300]
    upload = store.get_upload(upload_id)
    assert upload["status"] == "failed"
    # B7: the failure reason is persisted and surfaced on the detail page.
    assert upload.get("error")
    detail = client.get(f"/dashboard/uploads/{upload_id}")
    assert detail.status_code == 200
    assert "Ingestion failed" in detail.text


def test_unknown_ids_return_404_not_500(client):
    """Bad {id} routes must 404, never 500."""
    for path in [
        "/runs/does-not-exist",
        "/runs/does-not-exist/status",
        "/dashboard/uploads/does-not-exist",
    ]:
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 404, f"{path} -> {r.status_code}"
