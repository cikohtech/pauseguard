"""API test rig: the real FastAPI app and orchestrator logic, with stub agents (no model), a
pinned clock, memory state, a throwaway analytics database and a fake Firebase token check."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.agents.casefile_agent import CaseFileRequest, CaseFileRun, fallback_case_file
from app.agents.evidence_agent import EvidenceRequest, EvidenceRun
from app.agents.explainer_agent import ExplainRequest, ExplainRun, static_message
from app.agents.intel_agent import IntelRequest, IntelRun
from app.agents.orchestrator import Orchestrator
from app.api.deps import Services
from app.config import Settings
from app.data.memory_repo import MemoryStateRepo
from app.data.sqlite_repo import SCHEMA_PATH, SqliteAnalyticsRepo, SqliteTransactionRepo
from app.main import create_app
from app.models.schemas import EvidenceAnalysis, IntelResult, TokenUsage
from app.tools.evidence_store import LocalEvidenceStore
from tests.conftest import AS_OF

ADMIN_TOKEN = "test-admin-token"
CUSTOMER = {"Authorization": "Bearer anon-token"}
ANALYST = {"Authorization": "Bearer analyst-token"}
ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
CLAIMS: dict[str, dict[str, Any]] = {
    "anon-token": {"uid": "anon-1", "firebase": {"sign_in_provider": "anonymous"}},
    "analyst-token": {
        "uid": "analyst-1",
        "email": "daniel.lim@harbourbank.example",
        "role": "analyst",
        "firebase": {"sign_in_provider": "password"},
    },
}


def verify_token(token: str) -> dict[str, Any]:
    if token not in CLAIMS:
        raise ValueError("bad token")
    return CLAIMS[token]


def analysis(
    typology: str, conf: float, flags: list[dict[str, Any]], **kw: Any
) -> EvidenceAnalysis:
    return EvidenceAnalysis.model_validate(
        {
            "evidence_present": True,
            "summary": f"{typology} evidence.",
            "red_flags": flags,
            "typology_guess": typology,
            "typology_confidence": conf,
        }
        | kw
    )


TAN = analysis(
    "GOV_OFFICIAL_IMPERSONATION",
    0.99,
    [
        {"code": "SAFE_ACCOUNT", "severity": "HIGH", "quote": "转到安全账户", "evidence_index": 0,
         "box_2d": [495, 52, 517, 750]},
        {"code": "AUTHORITY_CLAIM", "severity": "HIGH", "quote": "我是MAS的李伟"},
    ],
    entities={
        "phones": ["+65 8000 0147"],
        "urls": ["https://mas-gov-verify.example/case/2231"],
        "accounts": ["123-45678-9"],
        "orgs": ["MAS"],
    },
)  # fmt: skip
RAJ = analysis(
    "JOB_TASK",
    0.95,
    [{"code": "PAY_TO_EARN", "severity": "HIGH", "quote": "top up S$450", "evidence_index": 0}],
    entities={"phones": ["+65 8000 0188"], "urls": ["https://t.me/joinchat/gold-slots"]},
)
AISYAH = analysis("NONE", 0.95, [])
BY_ACCOUNT = {"123-45678-9": TAN, "556-208417-390": RAJ, "436-905127-318": AISYAH}


@dataclass
class StubEvidence:
    delay: float = 0.0
    requests: list[EvidenceRequest] = field(default_factory=list)

    async def analyse(self, req: EvidenceRequest) -> EvidenceRun:
        self.requests.append(req)
        if self.delay:
            await asyncio.sleep(self.delay)
        assert req.transfer is not None
        result = BY_ACCOUNT.get(req.transfer.account_number, AISYAH)
        return EvidenceRun(result, False, 1, 12, TokenUsage(in_=1200, out=300))


class StubExplainer:
    async def explain(self, req: ExplainRequest) -> ExplainRun:
        msg = static_message(req.fusion.verdict, req.language, req.fusion)
        return ExplainRun(msg, True, False, 5, TokenUsage(in_=400, out=40))


class StubCaseFile:
    async def write(self, req: CaseFileRequest) -> CaseFileRun:
        return CaseFileRun(fallback_case_file(req), True, False, 7, TokenUsage(in_=900, out=150))


class StubIntel:
    async def investigate(self, req: IntelRequest, *, state: Any) -> IntelRun:
        result = IntelResult(watchlist_matches=req.watchlist_matches)
        return IntelRun(result, False, False, 1, TokenUsage())


class PinnedOrchestrator(Orchestrator):
    """The clock is pinned to the end of the synthetic history, so scores never drift."""

    async def start(self, req: Any, **kw: Any) -> Any:
        kw.setdefault("as_of", AS_OF)
        return await super().start(req, **kw)


def analytics_db(path: Path) -> SqliteAnalyticsRepo:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.close()
    return SqliteAnalyticsRepo(path)


def make_settings(tmp_path: Path, **kw: Any) -> Settings:
    base: dict[str, Any] = {
        "auth_disabled": False,
        "admin_reset_token": ADMIN_TOKEN,
        "agent_timeout_seconds": 5.0,
        "casefile_timeout_seconds": 5.0,
        "local_uploads_dir": tmp_path / "uploads",
        "upload_backend": "local",
        "gemini_model": "gemini-test",
    }
    return Settings(_env_file=None, **(base | kw))  # type: ignore[call-arg]


def build_services(
    tmp_path: Path,
    state: MemoryStateRepo,
    txn_repo: SqliteTransactionRepo,
    *,
    settings: Settings | None = None,
    orchestrator: Orchestrator | None = None,
    evidence: StubEvidence | None = None,
) -> Services:
    s = settings or make_settings(tmp_path)
    orch = orchestrator or PinnedOrchestrator(
        txn_repo=txn_repo,
        state=state,
        settings=s,
        evidence=evidence or StubEvidence(),  # type: ignore[arg-type]
        intel=StubIntel(),  # type: ignore[arg-type]
        explainer=StubExplainer(),  # type: ignore[arg-type]
        casefile=StubCaseFile(),  # type: ignore[arg-type]
    )
    return Services(
        settings=s,
        state=state,
        txn_repo=txn_repo,
        analytics=analytics_db(tmp_path / "analytics.db"),
        orchestrator=orch,
        store=LocalEvidenceStore(s.local_uploads_dir),
        verify_token=verify_token,
    )


def client_for(services: Services, *, raise_app_exceptions: bool = True) -> httpx.AsyncClient:
    app = create_app(services.settings, services=services)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def sse_events(body: str) -> list[dict[str, Any]]:
    """Parse an SSE body into [{"event": ..., "data": {...}}] (comments/pings skipped)."""
    out = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        event, data = None, []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if event:
            out.append({"event": event, "data": json.loads("\n".join(data))})
    return out
