# Demo evidence

The evidence each demo persona shares in the live demo (`docs/DEMO_SCRIPT.md`). It is rendered from
`data/generate/demo_evidence.json` with `make demo-evidence`. Everything is synthetic, and these files
are not part of the eval set.

| File | Persona | Transfer the persona makes | Expected |
|---|---|---|---|
| `tan_mas_chat.png` | Mrs Tan (`cust_001`, zh) | S$8,000 to **Lee Wei Investigation Acct**, Harbour Bank `123-45678-9`, LOCAL_BANK, note "case 2231" | RED: fake MAS officer, safe account, secrecy, deadline. The phone `+65 8000 0147` and the account are on the seed watchlist; `mas-gov-verify.example` is not, so Scam-Intel searches it. |
| `raj_job_chat.png`, `raj_job_chat.txt` | Raj (`cust_002`, en) | S$450 to **Ahmad Danial**, Orchid Trust Bank `556-208417-390`, LOCAL_BANK | AMBER in the demo script: a pay-to-earn job scam. The `.txt` file is the same chat for the "paste the message" step. No watchlist hits. |
| `aisyah_tenancy.pdf` | Aisyah (`cust_003`, en) | S$3,200 to **Wong Kah Wai**, Kampong Federal Bank `436-905127-318`, LOCAL_BANK, note "Bishan deposit" | GREEN: a signed tenancy agreement whose landlord, account and deposit match the transfer. |
