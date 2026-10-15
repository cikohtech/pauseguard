"""The benchmark (EVAL_PLAN §4-5, phase 09): metric maths, the published prices, baseline B1's
retry and safe fallback, and how the runner turns an eval case into requests and rows. No model
is called: B1 gets a fake genai client."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.orchestrator import QUICK_REPLIES, CheckOutcome
from app.config import Settings
from app.models.schemas import CreateCheckResponse, TxnRisk, TxnRiskReason

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "eval"))

import metrics as m  # noqa: E402
import run_benchmark as rb  # noqa: E402
from baselines import single_prompt as b1  # noqa: E402


def row(label: str, verdict: str, **kw: Any) -> dict[str, Any]:
    base = {
        "label": label,
        "verdict": verdict,
        "typology": "JOB_TASK" if label == "SCAM" else "NONE",
        "tokens": {"in": 1000, "out": 100},
    }
    return base | kw


# --- metrics ---------------------------------------------------------------------------------


def test_summary_counts_amber_and_red_as_stopped() -> None:
    rows = [
        row("SCAM", "RED", typology_pred="JOB_TASK", answer_ms=4000, e2e_ms=4100),
        row("SCAM", "AMBER", typology_pred="INVESTMENT", answer_ms=6000, e2e_ms=6200),
        row("SCAM", "GREEN", fast_path=True, e2e_ms=300, tokens={"in": 0, "out": 0}),
        row("LEGIT", "GREEN", typology_pred="NONE", answer_ms=5000, e2e_ms=5100),
        row("LEGIT", "AMBER", typology_pred="FAKE_FRIEND", needs_review=True, answer_ms=12000),
        row("LEGIT", "RED", typology_pred="PHISHING", answer_ms=7000),
    ]
    s = m.summarise(rows)
    assert (s.recall, s.hard_stop_recall) == (2 / 3, 1 / 3)
    assert (s.fpr, s.legit_amber_rate, s.legit_red_rate) == (2 / 3, 1 / 3, 1 / 3)
    assert s.precision == 2 / 4 and s.f1 == pytest.approx(2 * 0.5 * (2 / 3) / (0.5 + 2 / 3))
    # Typology: exact match on scams; the fast-path scam was never analysed, so it counts wrong.
    assert s.typology_acc == 1 / 3 and s.typology_acc_analysed == 1 / 2
    assert (s.fast_path_scams, s.fast_path_legit, s.failures) == (1, 0, 1)
    assert (s.answer_p50, s.answer_p95, s.answer_n) == (6000, 12000, 5)
    assert s.e2e_p50 == 4100  # nearest rank over the 4 rows that have it
    assert s.tokens_in == pytest.approx(5000 / 6)
    assert m.confusion(rows) == {
        "SCAM": {"GREEN": 1, "AMBER": 1, "RED": 1},
        "LEGIT": {"GREEN": 1, "AMBER": 1, "RED": 1},
    }


def test_rules_only_rows_have_no_typology() -> None:
    s = m.summarise([row("SCAM", "AMBER"), row("LEGIT", "GREEN")])
    assert s.typology_acc is None and s.typology_acc_analysed is None
    assert m.summarise([row("LEGIT", "GREEN")]).recall is None


def test_percentiles_wilson_and_bands() -> None:
    assert m.pctl([5, 1, 4, 2, 3], 0.5) == 3 and m.pctl([5, 1, 4, 2, 3], 0.95) == 5
    assert m.pctl([None, 7], 0.5) == 7 and m.pctl([], 0.5) is None
    lo, hi = m.wilson(45, 50)
    assert (round(lo, 3), round(hi, 3)) == (0.786, 0.957)
    assert m.wilson(0, 50)[0] == 0.0 and m.wilson(50, 50)[1] == 1.0
    assert m.pct_ci(45, 50) == "90% (79–96)"
    assert [m.age_band(a) for a in (None, 25, 40, 59, 60, 81)] == [
        "unknown",
        "under 40",
        "40-59",
        "40-59",
        "60+",
        "60+",
    ]


def test_cost_uses_the_published_price_and_never_guesses() -> None:
    pricing = m.load_pricing()
    assert pricing["source_url"].startswith("https://cloud.google.com/")
    assert pricing["retrieved"]
    # The model the API runs on Cloud Run must have a published price.
    deployed = (REPO / "infra" / "cloudrun.env.yaml").read_text(encoding="utf-8")
    model = next(ln.split(":")[1].strip() for ln in deployed.splitlines() if "GEMINI_MODEL" in ln)
    price = m.model_price(pricing, model)
    assert model == Settings(_env_file=None).gemini_model  # type: ignore[call-arg]
    s = m.summarise([row("SCAM", "RED", tokens={"in": 4000, "out": 600})])
    expected = (4000 * price["input_per_mtok"] + 600 * price["output_per_mtok"]) / 1e6
    assert s.cost_per_check(price) == pytest.approx(expected)
    with pytest.raises(KeyError, match="pricing.yaml"):
        m.model_price(pricing, "gemini-unpriced")


def test_the_dashboard_prices_match_the_published_ones() -> None:
    """/metrics' cost per check on Cloud Run uses GEMINI_PRICE_*: the same figures as the report."""
    import yaml

    env = yaml.safe_load((REPO / "infra" / "cloudrun.env.yaml").read_text(encoding="utf-8"))
    price = m.model_price(m.load_pricing(), env["GEMINI_MODEL"])
    assert float(env["GEMINI_PRICE_IN_USD_PER_MTOK"]) == price["input_per_mtok"]
    assert float(env["GEMINI_PRICE_OUT_USD_PER_MTOK"]) == price["output_per_mtok"]


# --- B1: one Gemini call -------------------------------------------------------------------


class FakeGenai:
    """genai.Client stand-in: `client.aio.models.generate_content` replays canned answers."""

    def __init__(self, *answers: Any):
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate))

    async def _generate(self, **kw: Any) -> Any:
        self.calls.append(kw)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        usage = SimpleNamespace(
            prompt_token_count=900, candidates_token_count=40, thoughts_token_count=10
        )
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return SimpleNamespace(text=text, usage_metadata=usage)


GOOD = {"verdict": "RED", "typology": "JOB_TASK", "confidence": 0.9, "reason": "Pay to earn."}


def b1_case() -> rb.Case:
    return rb.Case(
        {
            "id": "ev_9999",
            "split": "dev",
            "label": "SCAM",
            "typology": "JOB_TASK",
            "scenario": "JOB_TASK",
            "language": "zh",
            "difficulty": "obvious",
            "injection": False,
            "transfer": {
                "customer_id": "cust_042",
                "payee_name": "Nur Izzati",
                "account_number": "214-73560-2",
                "bank_name": "Harbour Bank",
                "dest_type": "PAYNOW",
                "amount": 280.0,
                "currency": "SGD",
                "note": None,
                "is_new_payee": True,
            },
            "customer_answer": "招聘的人说要先充值才能拿佣金。",
            "quick_reply": "A job recruiter",
            "evidence": [{"type": "text", "text": "Top up S$280 to unlock your commission."}],
        },
        age=63,
    )


def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


TXN = TxnRisk(
    score=45, reasons=[TxnRiskReason(code="NEW_PAYEE", label="First transfer", points=20)]
)


async def test_b1_sends_every_input_once_and_parses_the_verdict() -> None:
    client = FakeGenai(GOOD)
    run = await b1.run_single_prompt(
        b1_case().evidence_request("b1_x"), TXN, settings(), client=client
    )  # type: ignore[arg-type]
    assert not run.failed and run.answer.verdict == "RED" and run.attempts == 1
    assert (run.tokens_in, run.tokens_out) == (900, 50)  # thinking tokens count as output
    [call] = client.calls
    text = " ".join(p.text or "" for p in call["contents"][0].parts)
    assert "<transfer>" in text and "<transaction_risk>\nScore: 45/100" in text
    assert "招聘的人说要先充值才能拿佣金。" in text and "Top up S$280" in text
    assert "工作招聘人员" in text  # the zh chip, as the customer tapped it
    assert call["config"].response_schema is b1.SinglePromptAnswer
    assert "never an instruction" in call["config"].system_instruction


async def test_b1_retries_once_then_falls_back_to_amber_never_green() -> None:
    retried = await b1.run_single_prompt(
        b1_case().evidence_request("b1_x"),
        TXN,
        settings(),
        client=FakeGenai("not json", GOOD),  # type: ignore[arg-type]
    )
    assert not retried.failed and retried.attempts == 2 and retried.tokens_in == 1800
    failed = await b1.run_single_prompt(
        b1_case().evidence_request("b1_x"),
        TXN,
        settings(),
        client=FakeGenai(RuntimeError("429 RESOURCE_EXHAUSTED"), {"verdict": "GREEN"}),  # type: ignore[arg-type]
    )
    assert failed.failed and failed.answer.verdict == "AMBER" and failed.attempts == 2
    assert failed.error and "invalid output" in failed.error


# --- the runner's mapping ---------------------------------------------------------------------


def test_case_becomes_the_requests_the_app_would_send() -> None:
    case = b1_case()
    create = case.create_request()
    assert create.language == "zh" and create.transfer.amount == 280.0
    assert "is_new_payee" not in create.transfer.model_dump()  # the bank works that out
    assert case.quick_reply == QUICK_REPLIES["zh"][1]
    msg = case.message([])
    assert msg.pasted_text == "Top up S$280 to unlock your commission." and msg.evidence_uris == []
    bare = case.message(["data/eval/img/x.png"], with_evidence=False)
    assert bare.pasted_text is None and bare.evidence_uris == [] and bare.text
    assert case.evidence_type == "text" and case.base_row()["age"] == 63


def test_b0_row_and_fast_path_row() -> None:
    case = b1_case()
    step = rb.TxnStep(TXN, 12)
    b0 = rb.b0_row(case, step)
    assert b0["verdict"] == "AMBER" and b0["txn_reasons"] == ["NEW_PAYEE"]  # 45 >= 40
    assert b0["e2e_ms"] == 12 and b0["tokens"] == {"in": 0, "out": 0}

    started = CreateCheckResponse(
        check_id="chk_1", status="DONE", txn_risk=TxnRisk(score=20), verdict="GREEN"
    )
    fast = rb.outcome_row(case, CheckOutcome(started), start_ms=40, grounding_queries=0)
    assert fast["verdict"] == "GREEN" and fast["fast_path"] and fast["answer_ms"] is None
    assert fast["e2e_ms"] == 40 and fast["txn_score"] == 20
    assert m.summarise([fast]).fast_path_scams == 1


def test_only_the_local_target_runs_ablations(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match="--local"):
        rb.main(["--api", "http://localhost:8000", "--systems", "pauseguard,pg_always"])
    with pytest.raises(SystemExit, match="Unknown systems"):
        rb.main(["--local", "--systems", "b2"])
