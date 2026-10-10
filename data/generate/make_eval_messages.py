"""Draft the 160-case eval set (DATA_SPEC §4, EVAL_PLAN §3) and write it up for human review.

    python make_eval_messages.py plan                  # print the slot plan
    python make_eval_messages.py draft [--drafter X]   # -> data/eval/drafts.jsonl + REVIEW.md
    python make_eval_messages.py assemble              # after review + render -> cases.jsonl + hash
    python make_eval_messages.py verify                # the frozen test split is unchanged

**Plan.** The slots (label, typology or legit kind, language, evidence format, difficulty, split,
customer, counterpart phone, new or known payee) come from code with a fixed seed, so the mix in
DATA_SPEC §4 is exact and the case IDs don't reveal the label. Customers are real rows of the
synthetic bank (data/seed/*.csv, run `make seed-local` first), so `compute_txn_risk` works on them.

**Drafts.** Each slot is filled with a conversation, the customer's answer and the transfer:
- `--drafter gemini` sends the seed prompt (data/generate/prompts/) plus the slot to GEMINI_MODEL on
  Vertex AI with the `Draft` schema as `response_schema`.
- `--drafter library` (default) reads hand-written drafts from data/generate/eval_library/*.json,
  keyed by slot ID, written from the same prompts. The frozen set was made this way; see
  docs/DECISIONS.md (phase 02) for why.
Every draft is validated against `Draft` and against the fictional-entity rules before it is
written. A human then reviews data/eval/REVIEW.md before anything is rendered or frozen.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_schema import (  # noqa: E402
    IMAGE_FORMATS,
    CaseEvidence,
    CaseTransfer,
    Draft,
    DraftRecord,
    EvalCase,
    FixedPayee,
    Slot,
)

REPO = Path(__file__).resolve().parents[2]
SEED_DIR = REPO / "data" / "seed"
EVAL_DIR = REPO / "data" / "eval"
LIBRARY_DIR = Path(__file__).resolve().parent / "eval_library"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SEED = 42
PERSONAS = {"cust_001", "cust_002", "cust_003", "cust_004"}  # demo-only, never in the eval set

# --- The mix (DATA_SPEC §4) ---------------------------------------------------------------------
# Per group: slot count, Chinese slots, evidence formats, known-payee slots, customer filter.
# Totals: 80 SCAM + 80 LEGIT; 104 en / 56 zh; 96 image (chat/sms/email), 40 text, 16 pdf, 8 none.


@dataclass(frozen=True)
class Group:
    label: str
    scenario: str
    zh: int
    formats: dict[str, int]
    known: int = 0  # slots paying an existing payee (legit only)
    ages: tuple[int, int] = (18, 85)
    segment: str | None = None

    @property
    def n(self) -> int:
        return sum(self.formats.values())


GROUPS = [
    # SCAM (80): GOV 16, investment 16, job/task 16, phishing 10, e-commerce 8, fake friend 8,
    # romance 3, BEC 3.
    Group(
        "SCAM",
        "GOV_OFFICIAL_IMPERSONATION",
        7,
        {"chat": 7, "sms": 2, "text": 4, "pdf": 2, "none": 1},
        ages=(50, 85),
    ),
    Group("SCAM", "INVESTMENT", 6, {"chat": 9, "text": 4, "pdf": 2, "none": 1}, ages=(28, 70)),
    Group("SCAM", "JOB_TASK", 4, {"chat": 11, "text": 4, "pdf": 1}, ages=(18, 40)),
    Group("SCAM", "PHISHING", 3, {"sms": 4, "email": 2, "text": 3, "pdf": 1}),
    Group("SCAM", "ECOMMERCE", 3, {"chat": 5, "text": 2, "none": 1}, ages=(18, 50)),
    Group("SCAM", "FAKE_FRIEND", 3, {"chat": 5, "text": 2, "none": 1}, ages=(45, 85)),
    Group("SCAM", "ROMANCE", 1, {"chat": 2, "text": 1}, ages=(35, 70)),
    Group("SCAM", "BEC_INVOICE", 1, {"email": 1, "pdf": 2}, segment="SME_OWNER"),
    # LEGIT (80): ten hard-negative kinds, 8 each.
    Group("LEGIT", "RENT_DEPOSIT", 3, {"chat": 4, "text": 2, "pdf": 2}, ages=(22, 50)),
    Group("LEGIT", "NEW_CONTRACTOR", 3, {"chat": 4, "text": 2, "pdf": 2}, known=1, ages=(28, 85)),
    Group("LEGIT", "FAMILY_REQUEST", 3, {"chat": 5, "text": 2, "none": 1}, known=4),
    Group("LEGIT", "BANK_SMS", 3, {"sms": 5, "email": 1, "text": 2}, known=4),
    Group("LEGIT", "INVOICE", 2, {"email": 4, "text": 2, "pdf": 2}, known=5, segment="SME_OWNER"),
    Group(
        "LEGIT",
        "BROKER_TOPUP",
        3,
        {"email": 4, "chat": 1, "text": 2, "none": 1},
        known=6,
        ages=(25, 75),
    ),
    Group("LEGIT", "CHARITY", 3, {"chat": 2, "email": 2, "text": 2, "pdf": 1, "none": 1}, known=2),
    Group("LEGIT", "BILL_SPLIT", 3, {"chat": 5, "text": 2, "none": 1}, known=3, ages=(18, 45)),
    Group(
        "LEGIT", "TUITION", 3, {"chat": 3, "email": 2, "text": 2, "pdf": 1}, known=2, ages=(18, 60)
    ),
    Group("LEGIT", "FRIEND_NEW_NUMBER", 2, {"chat": 6, "text": 2}, known=3, ages=(20, 65)),
]
DEV_SHARE = 60 / 160  # dev 60 / test 100, stratified per group (30 + 30 dev)

# Prompt-injection slots (SECURITY_PRIVACY §1): (typology, language, format, preferred split).
INJECTIONS = [
    ("GOV_OFFICIAL_IMPERSONATION", "zh", "chat", "test"),
    ("JOB_TASK", "en", "chat", "test"),
    ("BEC_INVOICE", "en", "pdf", "test"),
    ("INVESTMENT", "en", "text", "dev"),
    ("PHISHING", "en", "email", "dev"),
]

# Known payees for legit kinds: which of the customer's existing payees fit the story.
BROKERS = {"Tidewater Securities", "Keystone Invest Brokerage", "Nimbus Crypto Exchange"}
SUPPLIERS = {
    "Sinar Wholesale Trading",
    "Golden Grain Supplies",
    "Jurong Packaging Works",
    "Eastline Logistics",
    "Prima Kitchen Equipment",
    "Bayview Printing Services",
}
BILLERS = {
    "City Power & Water",
    "Evergreen Life Assurance",
    "Bluewater General Insurance",
    "Kite Mobile",
    "Equator Telecom",
    "Nova Fibre Broadband",
}
CONTRACTORS = {"Ah Seng Renovation Works", "Greenleaf Aircon Servicing", "Harmony Movers"}
KNOWN_PAYEE_FILTER = {
    "FAMILY_REQUEST": lambda p, cats: "FAMILY" in cats,
    "BILL_SPLIT": lambda p, cats: "TRANSFER" in cats and p["dest_type"] in ("PAYNOW", "LOCAL_BANK"),
    "FRIEND_NEW_NUMBER": lambda p, cats: (
        "TRANSFER" in cats and p["dest_type"] in ("PAYNOW", "LOCAL_BANK")
    ),
    "BROKER_TOPUP": lambda p, cats: p["payee_name"] in BROKERS,
    "INVOICE": lambda p, cats: p["payee_name"] in SUPPLIERS,
    "BANK_SMS": lambda p, cats: p["payee_name"] in BILLERS,
    "CHARITY": lambda p, cats: p["payee_name"] == "Kindred Hearts Charity",
    "TUITION": lambda p, cats: p["payee_name"] == "Bright Minds Tuition Centre",
    "NEW_CONTRACTOR": lambda p, cats: p["payee_name"] in CONTRACTORS,
}

# --- Fictional-entity rules (prompts/scam_messages.md, "Hard rules") ------------------------------

PHONE_RE = re.compile(r"\+65[\s-]?\d{4}[\s-]?\d{4}")
ALLOWED_PHONE_RE = re.compile(r"^\+65 8000 0\d{3}$")
URL_RE = re.compile(r"\b(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s\"'，。）)]*)?", re.I)
EMAIL_RE = re.compile(r"\b[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
WATCHLIST_PHONES = {f"+65 8000 0{n}" for n in (112, 118, 125, 131, 139, 147, 153, 160, 166, 172)}
WATCHLIST_ACCOUNTS = {"123-45678-9", "123456789"}
WATCHLIST_DOMAIN_WORDS = (
    "quantayield",
    "auroramint",
    "bit-lagoon",
    "taskhub",
    "parcel-redelivery",
    "harbourbank-secure",
    "gov-refund-portal",
    "police-sg-case",
    "lovenest",
    "quickcash-tasks",
    "concert-tix",
    "mas-gov-verify",
)
REAL_BRANDS = re.compile(
    r"\b(whatsapp|telegram|wechat|facebook|instagram|tiktok|shopee|lazada|carousell|"
    r"singpost|dhl|fedex|binance|coinbase|paypal|dbs|posb|ocbc|uob|maybank|citibank|hsbc|"
    r"standard chartered)\b",
    re.I,
)
# Words that look like domains but are not (abbreviations with dots, amounts, times).
NOT_DOMAINS = re.compile(r"^(?:\d+(?:\.\d+)*|[a-z]\.[a-z]\.?|e\.g|i\.e|no\.|pte\.|ltd\.)$", re.I)


def text_of(draft: Draft) -> str:
    """Every string in the draft, for the rule checks."""
    return json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)


def rule_violations(slot: Slot, draft: Draft) -> list[str]:
    problems: list[str] = []
    blob = text_of(draft)
    for m in PHONE_RE.finditer(blob):
        phone = re.sub(r"[\s-]", "", m.group(0))
        pretty = f"{phone[:3]} {phone[3:7]} {phone[7:]}"
        if not ALLOWED_PHONE_RE.match(pretty):
            problems.append(f"phone outside +65 8000 0xxx: {m.group(0)}")
        if pretty in WATCHLIST_PHONES:
            problems.append(f"watchlisted phone: {pretty}")
    for m in EMAIL_RE.finditer(blob):
        if not m.group(1).lower().endswith(".example"):
            problems.append(f"email domain is not .example: {m.group(0)}")
    for m in URL_RE.finditer(blob):
        host = m.group(0).split("//")[-1].split("/")[0].lower()
        if "@" in blob[max(0, m.start() - 1) : m.start()] or NOT_DOMAINS.match(host):
            continue
        tld = host.rsplit(".", 1)[-1]
        if tld in {"com", "sg", "net", "org", "io", "co", "gov", "my", "cn", "app", "ly", "info"}:
            problems.append(f"real-looking domain: {m.group(0)}")
    low = blob.lower()
    problems += [f"watchlisted domain word: {w}" for w in WATCHLIST_DOMAIN_WORDS if w in low]
    acct = re.sub(r"[^0-9A-Za-z]", "", draft.transfer.account_number)
    if draft.transfer.account_number in WATCHLIST_ACCOUNTS or acct in WATCHLIST_ACCOUNTS:
        problems.append("watchlisted account")
    if brand := REAL_BRANDS.search(blob):
        problems.append(f"real brand name: {brand.group(0)}")
    if draft.difficulty != slot.difficulty:
        problems.append(f"difficulty {draft.difficulty} != slot {slot.difficulty}")
    if draft.evidence.format != slot.format:
        problems.append(f"format {draft.evidence.format} != slot {slot.format}")
    if slot.fixed_payee:
        fp = slot.fixed_payee
        t = draft.transfer
        if (t.payee_name, t.account_number) != (fp.payee_name, fp.account_number):
            problems.append("transfer does not use the slot's existing payee")
    return problems


# --- Plan ---------------------------------------------------------------------------------------


def _read(name: str) -> list[dict[str, str]]:
    path = SEED_DIR / f"{name}.csv"
    if not path.exists():
        sys.exit(f"{path} is missing: run `make seed-local` first")
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _largest_remainder(sizes: list[int], total: int) -> list[int]:
    raw = [n * DEV_SHARE for n in sizes]
    out = [int(r) for r in raw]
    order = sorted(range(len(sizes)), key=lambda i: raw[i] - out[i], reverse=True)
    for i in order[: total - sum(out)]:
        out[i] += 1
    return out


def build_plan(seed: int = SEED) -> list[Slot]:
    rng = random.Random(f"eval-plan:{seed}")
    customers = _read("customers")
    payees = _read("payees")
    txns = _read("transactions")
    scam_victims = {t["customer_id"] for t in txns if t["is_scam_label"].lower() in ("true", "1")}
    cats: dict[str, set[str]] = defaultdict(set)
    for t in txns:
        if t["payee_id"]:
            cats[t["payee_id"]].add(t["category"])
    payees_of: dict[str, list[dict[str, str]]] = defaultdict(list)
    for p in payees:
        payees_of[p["customer_id"]].append(p)
    pool = [
        c
        for c in customers
        if c["customer_id"] not in PERSONAS and c["customer_id"] not in scam_victims
    ]
    used: set[str] = set()

    def pick_customer(g: Group, lang: str, known: bool) -> tuple[dict[str, str], FixedPayee | None]:
        langs = {"zh"} if lang == "zh" else {"en", "ms", "ta"}
        cands = [
            c
            for c in pool
            if c["customer_id"] not in used
            and c["preferred_language"] in langs
            and g.ages[0] <= int(c["age"]) <= g.ages[1]
            and (g.segment is None or c["segment"] == g.segment)
        ]
        if known:
            ok = KNOWN_PAYEE_FILTER[g.scenario]
            cands = [
                c
                for c in cands
                if any(ok(p, cats[p["payee_id"]]) for p in payees_of[c["customer_id"]])
            ]
        if not cands:
            raise SystemExit(f"no customer for {g.scenario}/{lang}/known={known}")
        c = rng.choice(cands)
        used.add(c["customer_id"])
        if not known:
            return c, None
        ok = KNOWN_PAYEE_FILTER[g.scenario]
        p = rng.choice([p for p in payees_of[c["customer_id"]] if ok(p, cats[p["payee_id"]])])
        fixed = FixedPayee(
            payee_name=p["payee_name"],
            account_number=p["account_number"],
            bank_name=p["bank_name"],
            dest_type=p["dest_type"],
        )
        return c, fixed

    dev_counts = {
        "SCAM": _largest_remainder([g.n for g in GROUPS if g.label == "SCAM"], 30),
        "LEGIT": _largest_remainder([g.n for g in GROUPS if g.label == "LEGIT"], 30),
    }
    dev_iter = {k: iter(v) for k, v in dev_counts.items()}

    rows: list[dict[str, Any]] = []
    for g in GROUPS:
        formats = [f for f, k in g.formats.items() for _ in range(k)]
        rng.shuffle(formats)
        langs = ["zh"] * g.zh + ["en"] * (g.n - g.zh)
        rng.shuffle(langs)
        n_dev = next(dev_iter[g.label])
        splits = ["dev"] * n_dev + ["test"] * (g.n - n_dev)
        rng.shuffle(splits)
        diffs = ["obvious", "subtle"] * (g.n // 2) + ["subtle"] * (g.n % 2)
        rng.shuffle(diffs)
        known = [True] * g.known + [False] * (g.n - g.known)
        rng.shuffle(known)
        group_rows: list[dict[str, Any]] = [
            {
                "label": g.label,
                "scenario": g.scenario,
                "format": f,
                "language": lang,
                "split": s,
                "difficulty": d,
                "injection": False,
                "known": k,
            }
            for f, lang, s, d, k in zip(formats, langs, splits, diffs, known, strict=True)
        ]
        for typ, lang, fmt, split in INJECTIONS:
            if typ != g.scenario:
                continue
            match = [r for r in group_rows if (r["language"], r["format"]) == (lang, fmt)]
            match.sort(key=lambda r: r["split"] != split)
            if not match:
                raise SystemExit(f"no slot for injection case {typ}/{lang}/{fmt}")
            match[0]["injection"] = True
        for r in group_rows:
            cust, fixed = pick_customer(g, r["language"], r["known"])
            r["customer"] = cust
            r["fixed"] = fixed
        rows += group_rows

    rng.shuffle(rows)  # IDs don't reveal the label or typology
    slots: list[Slot] = []
    scam_n = legit_n = 0
    for i, r in enumerate(rows, start=1):
        if r["label"] == "SCAM":
            scam_n += 1
            phone = f"+65 8000 00{scam_n:02d}"
        else:
            legit_n += 1
            phone = f"+65 8000 02{legit_n:02d}"
        c = r["customer"]
        slots.append(
            Slot(
                id=f"ev_{i:04d}",
                split=r["split"],
                label=r["label"],
                scenario=r["scenario"],
                language=r["language"],
                format=r["format"],
                difficulty=r["difficulty"],
                injection=r["injection"],
                customer_id=c["customer_id"],
                customer_name=c["full_name"],
                customer_age=int(c["age"]),
                customer_segment=c["segment"],
                contact_phone=phone,
                is_new_payee=r["fixed"] is None,
                fixed_payee=r["fixed"],
            )
        )
    return slots


def mix_report(slots: list[Slot]) -> str:
    def count(key: Any) -> str:
        return ", ".join(f"{k} {v}" for k, v in sorted(Counter(map(key, slots)).items()))

    def count_images() -> str:
        images = Counter(s.format for s in slots if s.format in IMAGE_FORMATS)
        return ", ".join(f"{k} {v}" for k, v in sorted(images.items()))

    def ev_type(s: Slot) -> str:
        return "image" if s.format in IMAGE_FORMATS else s.format

    return "\n".join(
        [
            f"- Cases: {len(slots)} ({count(lambda s: s.label)})",
            f"- Split: {count(lambda s: s.split)}",
            f"- Language: {count(lambda s: s.language)}",
            f"- Evidence: {count(ev_type)}",
            f"- Image styles: {count_images()}",
            f"- Difficulty: {count(lambda s: s.difficulty)}",
            f"- Prompt-injection cases: {sum(s.injection for s in slots)}",
            f"- Known payees: {sum(not s.is_new_payee for s in slots)}",
        ]
    )


# --- Drafters -----------------------------------------------------------------------------------


def slot_brief(slot: Slot) -> dict[str, Any]:
    """What a drafter is told about a slot (no split, so drafts can't be tuned per split)."""
    brief = slot.model_dump(mode="json", exclude={"split", "id"})
    brief["customer_first_name"] = slot.customer_name.split()[0]
    return brief


def draft_library(slots: list[Slot]) -> dict[str, Draft]:
    raw: dict[str, Any] = {}
    for path in sorted(LIBRARY_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        dup = raw.keys() & data.keys()
        if dup:
            raise SystemExit(f"{path.name}: duplicate slot IDs {sorted(dup)}")
        raw.update(data)
    missing = [s.id for s in slots if s.id not in raw]
    if missing:
        raise SystemExit(f"library has no draft for {len(missing)} slots: {missing[:10]}...")
    return {s.id: Draft.model_validate(raw[s.id]) for s in slots}


def draft_gemini(slots: list[Slot]) -> dict[str, Draft]:  # pragma: no cover - needs Vertex AI
    from google import genai
    from google.genai import types

    model = os.environ.get("GEMINI_MODEL", "")
    if not model:
        raise SystemExit("GEMINI_MODEL is not set (see .env.example)")
    client = genai.Client()  # GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT / _LOCATION
    prompts = {
        "SCAM": (PROMPTS_DIR / "scam_messages.md").read_text(encoding="utf-8"),
        "LEGIT": (PROMPTS_DIR / "legit_messages.md").read_text(encoding="utf-8"),
    }
    level = os.environ.get("GEMINI_THINKING_LEVEL", "LOW")
    out: dict[str, Draft] = {}
    for slot in slots:
        request = (
            f"Slot:\n```json\n{json.dumps(slot_brief(slot), ensure_ascii=False, indent=2)}\n```"
        )
        for attempt in range(2):  # retry once on a schema or rule failure (CLAUDE.md rule 4)
            resp = client.models.generate_content(
                model=model,
                contents=[prompts[slot.label], request],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Draft,
                    thinking_config=types.ThinkingConfig(thinking_level=level),
                    seed=SEED,
                ),
            )
            try:
                draft = Draft.model_validate_json(resp.text or "")
                problems = rule_violations(slot, draft)
                if not problems:
                    out[slot.id] = draft
                    break
                request += f"\n\nYour previous draft broke these rules: {problems}. Fix them."
            except ValueError as e:
                request += f"\n\nYour previous draft was not valid JSON for the schema: {e}"
            if attempt == 1:
                raise SystemExit(f"{slot.id}: Gemini draft failed twice")
        print(f"  {slot.id} {slot.label} {slot.scenario} ✓", file=sys.stderr)
    return out


# --- Output -------------------------------------------------------------------------------------


def write_drafts(slots: list[Slot], drafts: dict[str, Draft], drafter: str) -> Path:
    bad = {s.id: p for s in slots if (p := rule_violations(s, drafts[s.id]))}
    if bad:
        for k, v in bad.items():
            print(f"{k}: {v}", file=sys.stderr)
        raise SystemExit(f"{len(bad)} drafts break the fictional-entity rules")
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    path = EVAL_DIR / "drafts.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for s in slots:
            rec = DraftRecord(slot=s, draft=drafts[s.id], drafter=drafter)
            f.write(json.dumps(rec.model_dump(mode="json"), ensure_ascii=False) + "\n")
    return path


def read_drafts(path: Path = EVAL_DIR / "drafts.jsonl") -> list[DraftRecord]:
    with path.open(encoding="utf-8") as f:
        return [DraftRecord.model_validate_json(line) for line in f if line.strip()]


def _evidence_md(draft: Draft) -> list[str]:
    ev = draft.evidence
    if ev.format in ("chat", "sms"):
        assert ev.header is not None
        sub = f" · {ev.header.subtitle}" if ev.header.subtitle else ""
        lines = [f"> **{ev.format.upper()}: {ev.header.name}**{sub}"]
        for b in ev.messages:
            if b.who == "day":
                lines.append(f"> — {b.text} —")
            else:
                who = "**them**" if b.who == "them" else "_me_"
                t = f" {b.time}" if b.time else ""
                lines.append(f"> {who}{t}: {b.text}".replace("\n", " / "))
        return lines
    if ev.format == "email":
        assert ev.email is not None
        e = ev.email
        lines = [
            f"> **EMAIL** From: {e.from_name} <{e.from_addr}> · To: {e.to} · {e.date}",
            f"> Subject: **{e.subject}**",
        ]
        lines += [f"> {p}" for p in e.body]
        lines += [f"> <sub>{p}</sub>" for p in e.footer]
        return lines
    if ev.format == "pdf":
        assert ev.document is not None
        d = ev.document
        lines = [f"> **PDF ({d.kind})**: {d.issuer} · {' · '.join(d.issuer_lines)}"]
        lines.append(f"> **{d.title}** {d.ref or ''} · {d.date}")
        if d.to_lines:
            lines.append(f"> To: {' / '.join(d.to_lines)}")
        lines += [f"> {p}" for p in d.body]
        lines += [
            f"> • {i.description}" + (f": {i.amount:,.2f}" if i.amount is not None else "")
            for i in d.items
        ]
        if d.total is not None:
            lines.append(f"> **Total: {d.total:,.2f}**")
        if d.payment:
            lines.append("> Payment: " + " · ".join(f"{k}: {v}" for k, v in d.payment.items()))
        lines += [f"> <sub>{p}</sub>" for p in d.footer]
        if d.signature:
            lines.append(f"> — {d.signature}")
        return lines
    if ev.format == "text":
        assert ev.text is not None
        return ["> **PASTED TEXT**"] + [f"> {ln}" for ln in ev.text.splitlines() if ln.strip()]
    return ["> _(no evidence: the customer only answers the question)_"]


def write_review(records: list[DraftRecord]) -> Path:
    slots = [r.slot for r in records]
    lines = [
        "# Eval set: human review",
        "",
        "Every draft for the 160-case eval set (`data/eval/drafts.jsonl`), grouped by label and "
        "scenario. Nothing is rendered or frozen until this file is approved (phase 02, task 3).",
        "",
        "**How to review (about 30–40 minutes).** Skim each case and ask: does it read like a real "
        "message? Is the label right (would a careful person agree this is a scam / genuine)? "
        "Is anything offensive, a real brand or a real number? To change a case, either edit its "
        "entry in `data/generate/eval_library/*.json` and run `make eval-drafts`, or write a line "
        "starting with `EDIT ev_0xxx:` under the case here and ask Claude Code to apply it. "
        'Then reply "approved".',
        "",
        f"Drafter: `{records[0].drafter}`. Seed prompts: `data/generate/prompts/`. "
        "Phones `+65 8000 00xx` are scammers, `+65 8000 02xx` legit counterparts; every domain "
        "is `.example`; none of them is on the seed watchlist.",
        "",
        "## Mix",
        "",
        mix_report(slots),
        "",
    ]
    order = [g.scenario for g in GROUPS]
    by_group: dict[str, list[DraftRecord]] = defaultdict(list)
    for r in records:
        by_group[r.slot.scenario].append(r)
    for label in ("SCAM", "LEGIT"):
        lines += [f"## {label}", ""]
        for scen in order:
            group = sorted(
                (r for r in by_group[scen] if r.slot.label == label), key=lambda r: r.slot.id
            )
            if not group:
                continue
            lines += [f"### {scen} ({len(group)})", ""]
            for r in group:
                s, d, t = r.slot, r.draft, r.draft.transfer
                tags: list[str] = [s.split, s.language, s.format, d.difficulty]
                if s.injection:
                    tags.append("**INJECTION**")
                payee = "known payee" if not s.is_new_payee else "new payee"
                lines += [
                    f"#### {s.id} · {' · '.join(tags)}",
                    "",
                    f"Customer {s.customer_id} ({s.customer_name}, {s.customer_age}, "
                    f"{s.customer_segment}) → **S${t.amount:,.2f}** to {t.payee_name} "
                    f"({t.bank_name} {t.account_number}, {t.dest_type}, {payee})"
                    + (f', note "{t.note}"' if t.note else ""),
                    "",
                    "\n>\n".join(_evidence_md(d)),
                    "",
                    f"Customer answer ({d.quick_reply}): “{d.customer_answer}”",
                    "",
                    f"_Reviewer note: {d.reviewer_note}_",
                    "",
                ]
    path = EVAL_DIR / "REVIEW.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# --- Assemble and freeze (EVAL_PLAN §3) ----------------------------------------------------------

CASES_PATH = EVAL_DIR / "cases.jsonl"
HASH_PATH = REPO / "eval" / "TEST_SPLIT_HASH"


def _norm_account(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", value).upper()


def to_case(rec: DraftRecord) -> EvalCase:
    s, d = rec.slot, rec.draft
    evidence: list[CaseEvidence] = []
    if s.format in IMAGE_FORMATS:
        path = f"data/eval/img/{s.id}.png"
        evidence.append(CaseEvidence(type="image", style=s.format, path=path))
    elif s.format == "pdf":
        evidence.append(
            CaseEvidence(type="pdf", style="document", path=f"data/eval/pdf/{s.id}.pdf")
        )
    elif s.format == "text":
        evidence.append(CaseEvidence(type="text", style="text", text=d.evidence.text))
    t = d.transfer
    return EvalCase(
        id=s.id,
        split=s.split,
        label=s.label,
        typology=s.scenario if s.label == "SCAM" else "NONE",
        scenario=s.scenario,
        language=s.language,
        difficulty=d.difficulty,
        injection=s.injection,
        transfer=CaseTransfer(
            customer_id=s.customer_id,
            payee_name=t.payee_name,
            account_number=t.account_number,
            bank_name=t.bank_name,
            dest_type=t.dest_type,
            amount=t.amount,
            note=t.note,
            is_new_payee=s.is_new_payee,
        ),
        customer_answer=d.customer_answer,
        quick_reply=d.quick_reply,
        evidence=evidence,
        # Injection forces RED in the fusion policy (SECURITY_PRIVACY §1).
        expected_verdict_min="GREEN" if s.label == "LEGIT" else ("RED" if s.injection else "AMBER"),
    )


def check_payees(cases: list[EvalCase]) -> list[str]:
    """`is_new_payee` must agree with the synthetic bank: known payees exist, new ones don't."""
    accounts: dict[str, set[str]] = defaultdict(set)
    for p in _read("payees"):
        accounts[p["customer_id"]].add(_norm_account(p["account_number"]))
    problems = []
    for c in cases:
        has = _norm_account(c.transfer.account_number) in accounts[c.transfer.customer_id]
        if has == c.transfer.is_new_payee:
            problems.append(
                f"{c.id}: is_new_payee={c.transfer.is_new_payee} but seed says {not has}"
            )
    return problems


def read_cases(path: Path = CASES_PATH) -> list[EvalCase]:
    with path.open(encoding="utf-8") as f:
        return [EvalCase.model_validate_json(line) for line in f if line.strip()]


def split_hash(cases: list[EvalCase], split: str = "test") -> str:
    """SHA-256 over the split's case records (canonical JSON, by ID) and its evidence file bytes."""
    h = hashlib.sha256()
    for c in sorted((c for c in cases if c.split == split), key=lambda c: c.id):
        h.update(json.dumps(c.model_dump(mode="json"), ensure_ascii=False, sort_keys=True).encode())
        h.update(b"\n")
        for ev in c.evidence:
            if ev.path:
                h.update(hashlib.sha256((REPO / ev.path).read_bytes()).hexdigest().encode())
                h.update(b"\n")
    return h.hexdigest()


def read_frozen_hash(path: Path = HASH_PATH) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            return line.strip()
    raise SystemExit(f"{path} has no hash line")


def assemble() -> list[EvalCase]:
    records = read_drafts()
    cases = [to_case(r) for r in records]
    missing = [
        ev.path for c in cases for ev in c.evidence if ev.path and not (REPO / ev.path).exists()
    ]
    if missing:
        raise SystemExit(f"{len(missing)} evidence files are missing (run `make eval-render`)")
    if problems := check_payees(cases):
        raise SystemExit("\n".join(problems))
    with CASES_PATH.open("w", encoding="utf-8") as f:
        for c in sorted(cases, key=lambda c: c.id):
            f.write(json.dumps(c.model_dump(mode="json"), ensure_ascii=False) + "\n")
    n_test = sum(c.split == "test" for c in cases)
    HASH_PATH.parent.mkdir(parents=True, exist_ok=True)
    HASH_PATH.write_text(
        f"{split_hash(cases)}\n"
        f"# SHA-256 of the test split of data/eval/cases.jsonl ({n_test} cases) and its evidence\n"
        "# files (see split_hash() in data/generate/make_eval_messages.py). The test split is\n"
        "# never used for tuning (EVAL_PLAN §6). Check it with `make eval-verify`.\n",
        encoding="utf-8",
    )
    return cases


# --- CLI ----------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="print the slot plan, grouped by scenario")
    p_plan.add_argument("--json", action="store_true", help="one slot per line as JSON")
    p_draft = sub.add_parser("draft", help="fill every slot -> drafts.jsonl + REVIEW.md")
    p_draft.add_argument("--drafter", choices=["library", "gemini"], default="library")
    sub.add_parser("review", help="rewrite REVIEW.md from drafts.jsonl")
    p_asm = sub.add_parser("assemble", help="drafts + evidence -> cases.jsonl + TEST_SPLIT_HASH")
    p_asm.add_argument("--force", action="store_true", help="replace a frozen test split")
    sub.add_parser("verify", help="check the frozen test split hash")
    args = ap.parse_args(argv)

    if args.cmd == "assemble":
        if HASH_PATH.exists() and not args.force:
            # EVAL_PLAN §6: a changed test split is a new test split, and the report must say so.
            raise SystemExit(f"{HASH_PATH.relative_to(REPO)} exists: the test split is frozen")
        cases = assemble()
        print(f"wrote {CASES_PATH.relative_to(REPO)} ({len(cases)} cases)")
        print(f"wrote {HASH_PATH.relative_to(REPO)}: {read_frozen_hash()}")
        return
    if args.cmd == "verify":
        got, want = split_hash(read_cases()), read_frozen_hash()
        if got != want:
            raise SystemExit(f"test split changed: {got} != frozen {want}")
        print(f"test split OK ({want[:16]}…)")
        return

    if args.cmd == "plan":
        slots = build_plan()
        if args.json:
            for s in slots:
                print(json.dumps(s.model_dump(mode="json"), ensure_ascii=False))
            return
        print(mix_report(slots))
        for g in GROUPS:
            print(f"\n## {g.label} {g.scenario}")
            for s in sorted((s for s in slots if s.scenario == g.scenario), key=lambda s: s.id):
                fp = s.fixed_payee
                known = (
                    f" KNOWN={fp.payee_name}|{fp.account_number}|{fp.bank_name}|{fp.dest_type}"
                    if fp
                    else ""
                )
                inj = " INJECTION" if s.injection else ""
                print(
                    f"{s.id} {s.split:4} {s.language} {s.format:5} {s.difficulty:7} "
                    f"{s.customer_id} {s.customer_name} ({s.customer_age}, {s.customer_segment}) "
                    f"{s.contact_phone}{known}{inj}"
                )
        return
    if args.cmd == "draft":
        slots = build_plan()
        drafts = draft_library(slots) if args.drafter == "library" else draft_gemini(slots)
        drafter = "library" if args.drafter == "library" else os.environ["GEMINI_MODEL"]
        path = write_drafts(slots, drafts, drafter)
        print(f"wrote {path.relative_to(REPO)} ({len(slots)} drafts)")
    review = write_review(read_drafts())
    print(f"wrote {review.relative_to(REPO)}")


if __name__ == "__main__":
    main()
