// Demo data for the Harbour Bank mock: what each persona's home screen shows, their saved payees,
// and the scenario the "Prefill demo scenario" link fills in (docs/DEMO_SCRIPT.md).
// Balances, payees and account numbers match the synthetic seed (data/generate/make_synthetic.py),
// so a saved payee really is a known payee to the risk engine. The recent transactions follow
// each persona's seeded pattern; the home screen doesn't query BigQuery (DECISIONS, phase 06).
// Everything here is synthetic.
import type { DestType, Transfer, UploadContentType } from '@/lib/api'

export const BANKS = [
  'Harbour Bank',
  'Orchid Trust Bank',
  'Kampong Federal Bank',
  'Riverside Savings Bank',
  'Lantern Commerce Bank',
] as const

export interface SavedPayee {
  name: string
  bank: string
  account: string
  dest_type: DestType
}

export type TxnKind = 'bill' | 'paynow' | 'income' | 'rent' | 'shopping' | 'transfer'

export interface RecentTxn {
  /** A proper name (payee or merchant); generic items use `labelKey` instead. */
  name?: string
  labelKey?: string
  kind: TxnKind
  amount: number // negative = money out
  daysAgo: number
}

export interface DemoEvidence {
  file: string // under /demo/ in web/public (copied from data/demo/)
  name: string
  type: UploadContentType
}

export interface DemoScenario {
  transfer: Transfer
  quickReplyIndex: number // into the API's quick replies
  answer: string
  evidence?: DemoEvidence
  pastedFile?: string // a .txt under /demo/, pasted as the chat
}

export interface DemoPersona {
  customer_id: string
  full_name: string
  age: number
  balance: number
  accountSuffix: string
  trustedPhone: string
  savedPayees: SavedPayee[]
  recent: RecentTxn[]
  scenario: DemoScenario
}

export const PERSONAS: DemoPersona[] = [
  {
    customer_id: 'cust_001',
    full_name: 'Tan Mei Ling',
    age: 67,
    balance: 42180.55,
    accountSuffix: '4471',
    trustedPhone: '+65 8000 0300',
    savedPayees: [
      { name: 'City Power & Water', bank: 'Harbour Bank', account: '997-42177-1', dest_type: 'MERCHANT' },
      { name: 'Kite Mobile', bank: 'Kampong Federal Bank', account: '996-891259-620', dest_type: 'MERCHANT' },
      { name: 'Town Council (S&CC)', bank: 'Harbour Bank', account: '594-13493-9', dest_type: 'MERCHANT' },
      { name: 'Evergreen Life Assurance', bank: 'Kampong Federal Bank', account: '671-814391-795', dest_type: 'MERCHANT' },
    ],
    recent: [
      { name: 'Kite Mobile', kind: 'bill', amount: -28.9, daysAgo: 3 },
      { name: 'Town Council (S&CC)', kind: 'bill', amount: -43.5, daysAgo: 8 },
      { labelKey: 'retirementPayout', kind: 'income', amount: 1180, daysAgo: 10 },
      { name: 'Evergreen Life Assurance', kind: 'bill', amount: -126, daysAgo: 21 },
      { name: 'City Power & Water', kind: 'bill', amount: -75.84, daysAgo: 29 },
    ],
    scenario: {
      transfer: {
        payee_name: 'Lee Wei Investigation Acct',
        account_number: '123-45678-9',
        bank_name: 'Harbour Bank',
        dest_type: 'LOCAL_BANK',
        amount: 8000,
        currency: 'SGD',
        note: 'case 2231',
      },
      quickReplyIndex: 0,
      answer: 'He says he is a MAS officer and my account is linked to money laundering, so I must move my money to a safe account.',
      evidence: { file: 'tan_mas_chat.png', name: 'WhatsApp_2026-10-11.png', type: 'image/png' },
    },
  },
  {
    customer_id: 'cust_002',
    full_name: 'Raj Kumar',
    age: 29,
    balance: 2340.2,
    accountSuffix: '2093',
    trustedPhone: '+65 8000 0301',
    savedPayees: [
      { name: 'Chua Siew Lan', bank: 'Riverside Savings Bank', account: '549-244599-505', dest_type: 'PAYNOW' },
      { name: 'Kumari Ramasamy', bank: 'Lantern Commerce Bank', account: '723-295010-136', dest_type: 'PAYNOW' },
      { name: 'Arun Nair', bank: 'Harbour Bank', account: '555-44199-6', dest_type: 'PAYNOW' },
      { name: 'Equator Telecom', bank: 'Riverside Savings Bank', account: '501-458631-219', dest_type: 'MERCHANT' },
    ],
    recent: [
      { labelKey: 'rideEarnings', kind: 'income', amount: 412.3, daysAgo: 1 },
      { name: 'Equator Telecom', kind: 'bill', amount: -35, daysAgo: 1 },
      { name: 'Arun Nair', kind: 'paynow', amount: -24, daysAgo: 2 },
      { labelKey: 'groceries', kind: 'shopping', amount: -36.4, daysAgo: 4 },
      { name: 'Chua Siew Lan', kind: 'rent', amount: -750, daysAgo: 9 },
    ],
    scenario: {
      transfer: {
        payee_name: 'Ahmad Danial',
        account_number: '556-208417-390',
        bank_name: 'Orchid Trust Bank',
        dest_type: 'LOCAL_BANK',
        amount: 450,
        currency: 'SGD',
        note: null,
      },
      quickReplyIndex: 1,
      answer: 'The recruiter says I need to top up to unlock my commission. Here is the message.',
      pastedFile: 'raj_job_chat.txt',
    },
  },
  {
    customer_id: 'cust_003',
    full_name: 'Nur Aisyah',
    age: 34,
    balance: 18640.75,
    accountSuffix: '7385',
    trustedPhone: '+65 8000 0302',
    savedPayees: [
      { name: 'Koh Residences Pte Ltd', bank: 'Orchid Trust Bank', account: '322-353945-406', dest_type: 'LOCAL_BANK' },
      { name: 'Salmah Ismail', bank: 'Harbour Bank', account: '358-12413-4', dest_type: 'LOCAL_BANK' },
      { name: 'Tidewater Securities', bank: 'Riverside Savings Bank', account: '168-677290-379', dest_type: 'LOCAL_BANK' },
      { name: 'Clara Pereira', bank: 'Harbour Bank', account: '588-35356-7', dest_type: 'PAYNOW' },
    ],
    recent: [
      { name: 'Nova Fibre Broadband', kind: 'bill', amount: -49.9, daysAgo: 2 },
      { name: 'Clara Pereira', kind: 'paynow', amount: -32, daysAgo: 4 },
      { name: 'Koh Residences Pte Ltd', kind: 'rent', amount: -2400, daysAgo: 10 },
      { labelKey: 'salary', kind: 'income', amount: 5150, daysAgo: 16 },
      { name: 'Bluewater General Insurance', kind: 'bill', amount: -88, daysAgo: 21 },
    ],
    scenario: {
      transfer: {
        payee_name: 'Wong Kah Wai',
        account_number: '436-905127-318',
        bank_name: 'Kampong Federal Bank',
        dest_type: 'LOCAL_BANK',
        amount: 3200,
        currency: 'SGD',
        note: 'Bishan deposit',
      },
      quickReplyIndex: 5,
      answer: "It's the deposit for the flat we're renting in Bishan. Tenancy agreement attached.",
      evidence: { file: 'aisyah_tenancy.pdf', name: 'Tenancy_Agreement_Bishan.pdf', type: 'application/pdf' },
    },
  },
]

export const findPersona = (id: string | null | undefined) =>
  PERSONAS.find((p) => p.customer_id === id) ?? null

/** Loads a demo evidence file from the app's own origin as a File, like a real pick. */
export async function loadDemoFile(ev: DemoEvidence): Promise<File> {
  const res = await fetch(`/demo/${ev.file}`)
  if (!res.ok) throw new Error(`demo file ${ev.file}: ${res.status}`)
  return new File([await res.blob()], ev.name, { type: ev.type })
}

export async function loadDemoText(file: string): Promise<string> {
  const res = await fetch(`/demo/${file}`)
  if (!res.ok) throw new Error(`demo file ${file}: ${res.status}`)
  return (await res.text()).trim()
}
