import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import '@/i18n'
import { EvidenceCard } from '@/customer/components/EvidenceCard'
import type { CustomerMessage, RedFlag } from '@/lib/api'

const flags: RedFlag[] = [
  { code: 'AUTHORITY_CLAIM', severity: 'HIGH', quote: '我是金管局的李伟', evidence_index: 0, box_2d: [180, 30, 280, 790] },
  { code: 'SAFE_ACCOUNT', severity: 'HIGH', quote: '转到金管局的安全账户', evidence_index: 0, box_2d: [460, 30, 550, 780] },
  { code: 'WATCHLIST_MATCH', severity: 'HIGH', quote: '+65 8000 0147', evidence_index: null, box_2d: null },
  { code: 'URGENCY', severity: 'MEDIUM', quote: 'Gold slots are limited today', evidence_index: 1, box_2d: null },
]
const message: CustomerMessage = {
  language: 'en',
  headline: 'We paused this',
  body: 'body',
  flag_explanations: [
    { code: 'AUTHORITY_CLAIM', text: 'Real officers never ask you to transfer money.' },
    { code: 'SAFE_ACCOUNT', text: "There is no such thing as a 'safe account'." },
    { code: 'WATCHLIST_MATCH', text: 'This number was reported before.' },
    { code: 'URGENCY', text: 'They rush you.' },
  ],
  next_steps: [],
}

function renderCard() {
  return render(
    <EvidenceCard
      verdict="RED"
      flags={flags}
      message={message}
      sources={[
        { kind: 'image', name: 'chat.png', url: 'blob:chat' },
        { kind: 'text', text: 'Hi Raj! Gold slots are limited today, many members are waiting.' },
      ]}
    />,
  )
}

test('draws a numbered box per boxed flag, positioned in percent of the image', () => {
  renderCard()
  const img = screen.getByRole('img', { name: /chat\.png, with 2 warning signs marked/ })
  expect(img).toHaveAttribute('src', 'blob:chat')

  const box1 = screen.getByRole('button', { name: 'Warning sign 1: Says they are an official' })
  expect(box1).toHaveStyle({ top: '18%', left: '3%', width: '76%', height: '10%' })
  expect(box1).toHaveTextContent('1')
  const box2 = screen.getByRole('button', { name: 'Warning sign 2: “Safe account”' })
  expect(box2).toHaveStyle({ top: '46%', left: '3%', width: '75%', height: '9%' })
  // flags without a box (watchlist, pasted text) get no box on the image
  expect(screen.queryByTestId('flag-box-3')).toBeNull()
  expect(screen.queryByTestId('flag-box-4')).toBeNull()
})

test('lists every flag with the same number, its title, the reviewed explanation and the quote', () => {
  renderCard()
  const items = within(screen.getByRole('list')).getAllByRole('listitem')
  expect(items).toHaveLength(4)
  expect(items[0]).toHaveTextContent('1Says they are an officialReal officers never ask you to transfer money.')
  expect(items[2]).toHaveTextContent('3Reported to us beforeThis number was reported before.“+65 8000 0147”')
  expect(items[3]).toHaveTextContent('4Rushing you')
})

test('each box is described by its list item, and selecting one highlights both', async () => {
  renderCard()
  const box = screen.getByTestId('flag-box-2')
  expect(box).toHaveAccessibleDescription(/There is no such thing as a 'safe account'/)
  expect(box).toHaveAttribute('aria-pressed', 'false')
  await userEvent.click(box)
  expect(box).toHaveAttribute('aria-pressed', 'true')
  const item = screen.getByRole('button', { name: /“Safe account”There is no such thing/ })
  expect(item).toHaveAttribute('aria-pressed', 'true')
})

test('marks the quoted part of pasted text with the flag number', () => {
  renderCard()
  const mark = document.querySelector('mark')!
  expect(mark).toHaveTextContent('Gold slots are limited today')
  expect(mark).toHaveTextContent(/^4/)
  expect(screen.getByText('The message you pasted')).toBeInTheDocument()
})

test('renders nothing without flags', () => {
  const { container } = render(<EvidenceCard verdict="AMBER" flags={[]} message={null} sources={[]} />)
  expect(container).toBeEmptyDOMElement()
})
