"""The eval set (DATA_SPEC §4, EVAL_PLAN §3): the plan is deterministic and has the spec's mix,
every draft keeps to the fictional-entity rules, the cases agree with the synthetic bank, the
evidence files exist, and the test split still matches its frozen hash."""

from __future__ import annotations

import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path

import pytest

from app.data.normalise import normalise_account, normalise_phone, normalise_watchlist_value

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "data" / "generate"))

import make_eval_messages as mem  # noqa: E402
from eval_schema import IMAGE_FORMATS, DraftRecord, EvalCase, Evidence  # noqa: E402

# DATA_SPEC §4. The acceptance criterion is "the mix within ±10% of the spec".
SCAM_MIX = {
    "GOV_OFFICIAL_IMPERSONATION": 16,
    "INVESTMENT": 16,
    "JOB_TASK": 16,
    "PHISHING": 10,
    "ECOMMERCE": 8,
    "FAKE_FRIEND": 8,
    "ROMANCE": 3,
    "BEC_INVOICE": 3,
}
EVIDENCE_SHARE = {"image": 0.60, "text": 0.25, "pdf": 0.10, "none": 0.05}
LANGUAGE_SHARE = {"en": 0.65, "zh": 0.35}
PHONE = re.compile(r"\+65[\s-]?\d{4}[\s-]?\d{4}")


def within(actual: float, target: float) -> bool:
    return abs(actual - target) <= max(1.0, 0.10 * target)


@pytest.fixture(scope="module")
def drafts() -> list[DraftRecord]:
    return mem.read_drafts()


@pytest.fixture(scope="module")
def cases() -> list[EvalCase]:
    if not mem.CASES_PATH.exists():
        if mem.HASH_PATH.exists():
            pytest.fail("eval/TEST_SPLIT_HASH exists but data/eval/cases.jsonl is missing")
        pytest.skip("eval set not assembled yet (waiting for the REVIEW.md sign-off)")
    return mem.read_cases()


@pytest.fixture
def seeded(seed_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the plan at the test's own synthetic bank (data/seed/ is git-ignored)."""
    monkeypatch.setattr(mem, "SEED_DIR", seed_dir)
    return seed_dir


def watchlist_ids() -> set[str]:
    entries = json.loads((REPO / "data" / "seed" / "watchlist.json").read_text())["entries"]
    return {normalise_watchlist_value(e["type"], e["value"]) for e in entries}


# --- Plan and drafts ----------------------------------------------------------------------------


def test_plan_is_deterministic_and_matches_the_drafts(
    seeded: Path, drafts: list[DraftRecord]
) -> None:
    plan = mem.build_plan()
    assert plan == mem.build_plan()
    assert plan == [d.slot for d in drafts]  # drafts.jsonl was built from this exact plan


def test_plan_has_the_spec_mix(seeded: Path) -> None:
    plan = mem.build_plan()
    assert len(plan) == 160
    assert Counter(s.label for s in plan) == {"SCAM": 80, "LEGIT": 80}
    assert Counter((s.label, s.split) for s in plan) == {
        ("SCAM", "dev"): 30,
        ("SCAM", "test"): 50,
        ("LEGIT", "dev"): 30,
        ("LEGIT", "test"): 50,
    }
    assert Counter(s.scenario for s in plan if s.label == "SCAM") == SCAM_MIX
    legit = Counter(s.scenario for s in plan if s.label == "LEGIT")
    assert len(legit) == 10 and set(legit.values()) == {8}
    langs = Counter(s.language for s in plan)
    assert all(within(langs[k], v * 160) for k, v in LANGUAGE_SHARE.items())
    ev = Counter("image" if s.format in IMAGE_FORMATS else s.format for s in plan)
    assert all(within(ev[k], v * 160) for k, v in EVIDENCE_SHARE.items())
    assert len({s.id for s in plan}) == 160
    assert len({s.customer_id for s in plan}) == 160  # one case per customer
    assert not {s.customer_id for s in plan} & {"cust_001", "cust_002", "cust_003", "cust_004"}


def test_injection_cases(seeded: Path) -> None:
    inj = [s for s in mem.build_plan() if s.injection]
    assert len(inj) == 5
    assert all(s.label == "SCAM" for s in inj)
    assert len({s.scenario for s in inj}) == 5


def test_every_draft_keeps_the_fictional_entity_rules(drafts: list[DraftRecord]) -> None:
    problems = {d.slot.id: p for d in drafts if (p := mem.rule_violations(d.slot, d.draft))}
    assert problems == {}


def test_injection_drafts_contain_injection_text(drafts: list[DraftRecord]) -> None:
    marker = re.compile(r"ignore (your |all )?previous instructions|忽略之前", re.I)
    for d in drafts:
        has = bool(marker.search(mem.text_of(d.draft)))
        assert has == d.slot.injection, d.slot.id


def test_the_rule_checker_catches_real_entities(drafts: list[DraftRecord]) -> None:
    rec = next(d for d in drafts if d.slot.format == "chat")
    bad = rec.draft.model_copy(deep=True)
    bad.evidence.messages[
        0
    ].text += " Call +65 9123 4567, visit pay-now.com via WhatsApp, mail x@gmail.com, +65 8000 0147"
    problems = " ".join(mem.rule_violations(rec.slot, bad))
    for expected in ("9123", "pay-now.com", "WhatsApp", "gmail.com", "watchlisted phone"):
        assert expected in problems


def test_no_eval_entity_is_on_the_watchlist(drafts: list[DraftRecord]) -> None:
    """The benchmark measures the conversation, not watchlist recall (see DECISIONS.md)."""
    seeded_ids = watchlist_ids()
    for d in drafts:
        blob = mem.text_of(d.draft)
        phones = {normalise_phone(m.group(0)) for m in PHONE.finditer(blob)}
        assert not phones & seeded_ids, d.slot.id
        assert normalise_account(d.draft.transfer.account_number) not in seeded_ids, d.slot.id


# --- Assembled cases ----------------------------------------------------------------------------


def test_cases_are_the_assembled_drafts(cases: list[EvalCase], drafts: list[DraftRecord]) -> None:
    assert sorted(cases, key=lambda c: c.id) == sorted(
        (mem.to_case(d) for d in drafts), key=lambda c: c.id
    )
    assert all(c.expected_verdict_min == "GREEN" for c in cases if c.label == "LEGIT")
    assert all(c.typology == "NONE" for c in cases if c.label == "LEGIT")
    assert all(c.expected_verdict_min == "RED" for c in cases if c.injection)


def test_is_new_payee_agrees_with_the_synthetic_bank(cases: list[EvalCase], seeded: Path) -> None:
    assert mem.check_payees(cases) == []
    assert Counter(c.transfer.is_new_payee for c in cases) == {True: 130, False: 30}


def test_evidence_files_render(cases: list[EvalCase]) -> None:
    for c in cases:
        for ev in c.evidence:
            if ev.type == "text":
                assert ev.text
                continue
            assert ev.path is not None
            data = (REPO / ev.path).read_bytes()
            if ev.type == "image":
                assert data[:8] == b"\x89PNG\r\n\x1a\n", ev.path
                assert struct.unpack(">II", data[16:24]) == (1080, 1920), ev.path
            else:
                assert data[:5] == b"%PDF-", ev.path


def test_test_split_matches_the_frozen_hash(cases: list[EvalCase]) -> None:
    assert mem.split_hash(cases) == mem.read_frozen_hash()


# --- Demo evidence (data/demo/) -----------------------------------------------------------------


def test_demo_evidence_exists_and_matches_the_story() -> None:
    spec = json.loads((REPO / "data/generate/demo_evidence.json").read_text())["files"]
    by_customer = {f["transfer"]["customer_id"]: f for f in spec}
    assert set(by_customer) == {"cust_001", "cust_002", "cust_003"}
    for f in spec:
        assert (REPO / f["output"]).stat().st_size > 10_000, f["output"]
    seeded_ids = watchlist_ids()

    def entities(f: dict) -> set[str]:
        blob = json.dumps(f["evidence"], ensure_ascii=False)
        ids = {normalise_phone(m.group(0)) for m in PHONE.finditer(blob)}
        return ids | {normalise_account(f["transfer"]["account_number"])}

    # Mrs Tan: her scammer's phone and mule account are seeded (WATCHLIST_MATCH in the demo),
    # but her domain is not, so Scam-Intel has something to search. Raj and Aisyah: no hits.
    tan = by_customer["cust_001"]
    assert {"+6580000147", "123456789"} <= entities(tan) & seeded_ids
    assert "mas-gov-verify.example" in json.dumps(tan["evidence"])
    assert "mas-gov-verify.example" not in seeded_ids
    assert not entities(by_customer["cust_002"]) & seeded_ids
    assert not entities(by_customer["cust_003"]) & seeded_ids
    assert Evidence.model_validate(by_customer["cust_003"]["evidence"]).format == "pdf"
