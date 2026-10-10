# Eval set

There are 160 labelled cases (80 scams, 80 legitimate hard negatives) for the benchmark in `docs/EVAL_PLAN.md`. They are split into **dev (60)** for tuning and **test (100)**, which is reported and never tuned on. Everything is synthetic: fictional names, `+65 8000 0xxx` numbers, `.example` domains and the fictional Harbour Bank.

| File | What it is |
|---|---|
| `cases.jsonl` | The cases (schema: `EvalCase` in `data/generate/eval_schema.py`): label, typology, language, the transfer (a real customer of the synthetic bank), the customer's answer, and the evidence. |
| `img/`, `pdf/` | Evidence rendered from the drafts: 96 phone screenshots (1080×1920, generic chat/SMS/email styling) and 16 A4 documents. Pasted-text evidence is inline in `cases.jsonl`. |
| `drafts.jsonl` | The planned slot plus the draft behind every case. |
| `REVIEW.md` | Every draft, written out for the human review that signed the set off on 10 Oct 2026. |
| `../../eval/TEST_SPLIT_HASH` | SHA-256 over the test cases and their evidence files. Check it with `make eval-verify`. |

How it was made: a seeded plan (`data/generate/make_eval_messages.py plan`) fixed the mix from DATA_SPEC §4. The drafts follow the seed prompts in `data/generate/prompts/` and are stored in `data/generate/eval_library/`. They were checked against the fictional-entity rules, reviewed by a human, rendered (`render_chats.py`, Playwright) and assembled (`make eval-dataset`). The reasons for each choice are in `docs/DECISIONS.md` (phase 02). The set is frozen: the render and assemble steps refuse to overwrite it without `--force`, and changing the test split means reporting a new one (EVAL_PLAN §6).

Mix: GOV impersonation 16, investment 16, job/task 16, phishing 10, e-commerce 8, fake friend 8, romance 3, BEC invoice 3. On the legit side there are 10 kinds × 8 (rent deposit, new contractor, family request, genuine bank SMS, invoice, broker top-up, charity, bill split, tuition, genuine new-number friend). The set has 104 English and 56 Chinese cases, 5 prompt-injection cases, and 81 "subtle" and 79 "obvious" cases. No phone number, account or domain in it is on the seed watchlist.
