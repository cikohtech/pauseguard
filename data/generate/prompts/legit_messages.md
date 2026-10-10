# Seed prompt: legitimate payments (hard negatives) for the PauseGuard eval set

You are writing **synthetic test data** for a bank's anti-scam research prototype. Each request gives
you one *slot* (a legitimate payment kind, a language, an evidence format, a customer profile and
sometimes a fixed payee). You write the message or document behind a **genuine** payment, the
customer's short answer to "Who asked you to make this payment?", and the transfer.

These are **hard negatives**: real payments that a nervous fraud system might stop. They should share
surface features with scams (a new payee, a large amount, a request for money, a new phone number, an
urgent tone, a bank SMS) while the context stays **consistent and verifiable**. The detector should
let them through. Never put a genuine red flag in a legit draft: no safe account, no pay-to-earn, no
remote-access app, no secrecy request, no guaranteed returns, no look-alike domain, no payee-name
mismatch, no instruction to ignore the bank.

## Hard rules

Same fictional-entity rules as `scam_messages.md`:
- Phone numbers `+65 8000 02xx` (the slot gives the number). Websites and emails `.example` only.
- The customer's bank is **Harbour Bank**; other banks are the fictional local/overseas banks listed
  there. Companies, schools, charities, agencies and apps are invented.
- People are invented.
- Keep it short (same length limits). Chinese slots use Simplified Chinese as written in Singapore.

## What makes it legitimate (pick what fits)

- The payee name matches the person or business in the message and on the document.
- The amount matches the document (invoice total, deposit = one month's rent, fee schedule).
- There is history or an independent check: "as discussed when we met at the flat", "I called your
  old number and you picked up", a quotation the customer asked for, an agency with a licence number.
- A genuine bank message tells the customer to use the app or the number on the back of their card,
  never a link, and never asks them to transfer money to "protect" it.
- Family requests have normal context (shared plans, a known event), no secrecy, no new account.

## Kinds (8 slots each)

**RENT_DEPOSIT.** A landlord or a property agent (with an agency name and a CEA-style licence number
such as `R0xxxxxH`) after a viewing; a tenancy agreement or a summary; deposit of 1–2 months' rent to
the landlord's named account. Subtle version: the agent says "please pay the deposit today, another
couple is keen" (urgent, but consistent and after a viewing).

**NEW_CONTRACTOR.** Renovation, aircon, plumber, movers or a cleaner the customer found and met; a
quotation with itemised work and a deposit or progress payment to the company account. Subtle:
first-time payee, larger amount, WhatsApp-style chat.

**FAMILY_REQUEST.** A child, parent or sibling asking for money with normal context (school trip,
helping with a hospital bill that the family already knows about, sharing the cost of a gift). Known
or new payee in the family member's own name. Subtle: from a new account ("I opened a new account
for my salary"), but in an ongoing chat with shared details.

**BANK_SMS.** A genuine Harbour Bank SMS or email: a bill reminder, a card statement, a transaction
alert, a fixed-deposit maturity notice. It never contains a link, and says "via the Harbour Bank app"
or "call the number on the back of your card". The customer then pays a bill or moves money between
their own accounts. Subtle: alarming wording ("unusual login detected, if this wasn't you, lock your
card in the app").

**INVOICE.** A real-looking invoice from a supplier the business already uses, with the same bank
details as before, or a new supplier with a consistent quotation → PO → invoice trail. SME owners.

**BROKER_TOPUP.** A licensed brokerage (Tidewater Securities, Keystone Invest Brokerage) or the legit
exchange "Nimbus Crypto Exchange": a contract note, a margin or settlement reminder from the broker's
own domain, or the customer's own plan to buy ETFs. Amounts S$1,000–S$30,000. No guaranteed returns.

**CHARITY.** A donation appeal or receipt from a registered charity (UEN or charity registration
number), a temple, mosque or church building fund, or a colleague's charity run. No pressure.

**BILL_SPLIT.** Friends or colleagues splitting dinner, a holiday villa, a group gift or concert tickets
bought by one person. The amounts add up. Subtle: an urgent "pay me back today pls, my card bill is
due" from a known friend in a group chat.

**TUITION.** Tuition centre, music school, enrichment class or university fees: a term invoice with
the student's name, or a tutor's message after classes already took place.

**FRIEND_NEW_NUMBER.** A **genuine** "new number" message. Consistent context makes it legit: the friend
gives a reason (changed telco, phone lost) and shared details the customer can verify, the customer
called them or met them, and the money is ordinary (paying back the friend who bought concert
tickets, chipping in for a wedding gift) to the friend's own name. No urgent loan to a third party.

## Output (JSON)

Same schema as `scam_messages.md`, with `quick_reply` from the same list (legit payments usually use
"A friend or family member", "A seller" or "No one, it's my own payment"), and `reviewer_note`
explaining why the payment is genuine despite the scary surface.
Return only the JSON.
