"""End to end through the API with the real agents (live Gemini on Vertex AI), as the customer
app and the console do it: start -> sign + PUT the demo evidence -> answer -> verdict, then the
analyst's REPORT_SCAM. Run: `uv run pytest -m live -k api_live` (about 1 minute, a few cents)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.scenarios import SCENARIOS
from app.config import REPO_ROOT, get_settings
from app.data.memory_repo import MemoryStateRepo
from app.data.seed import seed_state
from app.data.sqlite_repo import SqliteTransactionRepo
from tests.api_support import ANALYST, CUSTOMER, PinnedOrchestrator, build_services, client_for

pytestmark = pytest.mark.live
CONTENT_TYPES = {".png": "image/png", ".pdf": "application/pdf"}


@pytest.mark.parametrize("key", ["tan", "raj", "aisyah"])
async def test_demo_scenario_through_the_api(
    key: str, tmp_path: Path, seed_dir: Path, sqlite_repo: SqliteTransactionRepo
) -> None:
    settings = get_settings().model_copy(
        update={
            "auth_disabled": False,
            "upload_backend": "local",
            # Inside the repo: the evidence agent reads local files only from there.
            "local_uploads_dir": REPO_ROOT / ".local_uploads",
        }
    )
    state = MemoryStateRepo()
    await seed_state(state, seed_dir)
    orch = PinnedOrchestrator(txn_repo=sqlite_repo, state=state, settings=settings)
    services = build_services(tmp_path, state, sqlite_repo, settings=settings, orchestrator=orch)
    sc = SCENARIOS[key]

    async with client_for(services) as c:
        started = await c.post(
            "/api/v1/checks", json=sc.create_request().model_dump(mode="json"), headers=CUSTOMER
        )
        assert started.status_code == 201 and started.json()["status"] == "CHECKIN"
        check_id = started.json()["check_id"]

        uris = []
        for path in sc.evidence_uris:
            file = REPO_ROOT / path
            sign = await c.post(
                "/api/v1/uploads/sign",
                json={
                    "check_id": check_id,
                    "filename": file.name,
                    "content_type": CONTENT_TYPES[file.suffix],
                },
                headers=CUSTOMER,
            )
            signed = sign.json()
            put = await c.put(
                signed["upload_url"], content=file.read_bytes(), headers=signed["headers"]
            )
            assert put.status_code == 200
            uris.append(signed["gcs_uri"])

        msg = sc.message(evidence_uris=tuple(uris)).model_dump(mode="json", exclude_none=True)
        r = await c.post(f"/api/v1/checks/{check_id}/messages", json=msg, headers=CUSTOMER)
        body = r.json()
        assert r.status_code == 200, r.text
        assert body["verdict"] in sc.expected, body
        assert body["customer_message"]["headline"]

        if key == "tan":
            decision = await c.post(
                f"/api/v1/cases/{body['case_id']}/decision",
                json={"action": "REPORT_SCAM", "note": "live test"},
                headers=ANALYST,
            )
            assert decision.status_code == 200 and decision.json()["watchlist_added"] >= 2
    await services.drain()
