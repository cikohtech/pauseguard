// The customer app (/app) in Chromium: the three demo scenarios screen by screen, an axe scan
// (WCAG 2.1 A + AA) on every screen, the evidence boxes' real layout, and a keyboard-only run.
// Screenshots land in test-results/screens/ for review.
import { expect, test, type Locator, type Page } from '@playwright/test'

import { scan } from './axe'
import { fakeApi } from './fixtures'

async function startTransfer(page: Page, persona: RegExp, slug: string) {
  await page.goto('/app')
  await scan(page, 'picker')
  await page.getByRole('button', { name: persona }).click()
  await scan(page, `home-${slug}`)
  await page.getByRole('link', { name: /^(Transfer|转账)/ }).first().click()
  await page.getByRole('button', { name: /Prefill demo scenario|填入演示情景/ }).click()
  await scan(page, `transfer-${slug}`)
  await page.getByRole('button', { name: /Review transfer|核对转账/ }).click()
  await scan(page, `review-${slug}`)
  await page.getByRole('button', { name: /^(Send|发送)/ }).click()
  return page.getByRole('dialog', { name: /Quick safety check|快速安全确认/ })
}

test('Mrs Tan (Chinese): screenshot evidence → RED with numbered boxes on her screenshot', async ({ page }) => {
  const api = await fakeApi(page, { holdAnalysis: true })
  const sheet = await startTransfer(page, /陈美玲女士|Mrs Tan/, 'tan')
  await scan(page, 'checkin-tan')
  await sheet.getByRole('button', { name: '使用演示答案' }).click()
  await expect(sheet.getByRole('img', { name: 'WhatsApp_2026-10-11.png' })).toBeVisible()
  await expect(sheet.getByRole('radio', { name: '政府官员' })).toBeChecked()
  await scan(page, 'checkin-tan-filled')

  await sheet.getByRole('button', { name: '马上检查' }).click()
  await expect(page.getByTestId('analysing')).toBeVisible()
  await scan(page, 'analysing-tan')
  api.release()

  await expect(page.getByTestId('verdict-RED')).toBeVisible()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('为您暂停转账，保障资金安全')
  await expect(page.getByRole('link', { name: '拨打 1799 反诈骗热线' })).toHaveAttribute('href', 'tel:1799')
  await expect(page.getByRole('button', { name: /继续付款/ })).toHaveCount(0)

  // The boxes are drawn inside the screenshot, at the box_2d positions.
  const img = page.getByRole('img', { name: /WhatsApp_2026-10-11\.png/ })
  await img.scrollIntoViewIfNeeded()
  const ib = (await img.boundingBox())!
  for (const [n, [ymin, xmin, ymax, xmax]] of [
    [1, [205, 50, 285, 760]],
    [4, [785, 50, 830, 760]],
  ] as const) {
    const bb = (await page.getByTestId(`flag-box-${n}`).boundingBox())!
    expect(bb.y).toBeCloseTo(ib.y + (ymin / 1000) * ib.height, 0)
    expect(bb.x).toBeCloseTo(ib.x + (xmin / 1000) * ib.width, 0)
    expect(bb.width).toBeCloseTo(((xmax - xmin) / 1000) * ib.width, 0)
    expect(bb.height).toBeCloseTo(((ymax - ymin) / 1000) * ib.height, 0)
  }
  await scan(page, 'verdict-red-tan')

  const sent = api.requests.find((r) => r.path.endsWith('/messages'))!
  expect(sent.body).toMatchObject({ quick_reply: '政府官员', evidence_uris: [expect.stringMatching(/^gs:\/\//)] })
  expect(api.requests.find((r) => r.path === '/checks')!.body).toMatchObject({ customer_id: 'cust_001', language: 'zh' })
})

test('Raj: pasted chat → AMBER, the confirm dialog, then a 24-hour pause', async ({ page }) => {
  const api = await fakeApi(page)
  const sheet = await startTransfer(page, /Raj Kumar/, 'raj')
  await sheet.getByRole('button', { name: 'Use the demo answer' }).click()
  await expect(sheet.getByLabel('The message you received')).toHaveValue(/Kelly from TaskStar/)
  await sheet.getByRole('button', { name: 'Check now' }).click()

  await expect(page.getByTestId('verdict-AMBER')).toBeVisible()
  await expect(page.locator('mark')).toHaveCount(3)
  await scan(page, 'verdict-amber-raj')

  await page.getByRole('button', { name: 'I understand the risk, continue' }).click()
  const dialog = page.getByRole('dialog', { name: 'Send this payment anyway?' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Go back' })).toBeFocused()
  await scan(page, 'confirm-raj')
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()

  await page.getByRole('button', { name: 'Pause for 24 hours' }).click()
  await expect(page.getByTestId('outcome-paused')).toBeVisible()
  await scan(page, 'paused-raj')
  expect(api.requests.filter((r) => r.path.endsWith('/choice')).map((r) => r.body)).toEqual([
    { choice: 'COOL_OFF', confirmed: false },
  ])
})

test('Aisyah: tenancy PDF → GREEN, then the transfer goes through', async ({ page }) => {
  const api = await fakeApi(page)
  const sheet = await startTransfer(page, /Nur Aisyah/, 'aisyah')
  await sheet.getByRole('button', { name: 'Use the demo answer' }).click()
  await expect(sheet.getByText('Tenancy_Agreement_Bishan.pdf')).toBeVisible()
  await sheet.getByRole('button', { name: 'Check now' }).click()

  await expect(page.getByTestId('verdict-GREEN')).toBeVisible()
  await scan(page, 'verdict-green-aisyah')
  await expect(page.getByTestId('outcome-sent')).toBeVisible({ timeout: 5000 })
  await scan(page, 'sent-aisyah')
  expect(api.requests.some((r) => r.method === 'PUT' && r.path.endsWith('Tenancy_Agreement_Bishan.pdf'))).toBe(true)
})

/** Presses Tab until `target` has focus (fails if it is not reachable by keyboard). */
async function tabTo(page: Page, target: Locator, max = 40) {
  for (let i = 0; i < max; i++) {
    if (await target.evaluate((el) => el === document.activeElement)) return
    await page.keyboard.press('Tab')
  }
  throw new Error(`not reachable with Tab: ${target}`)
}

test('keyboard only: Raj from the persona picker to the AMBER verdict', async ({ page }) => {
  await fakeApi(page)
  await page.goto('/app')
  await tabTo(page, page.getByRole('button', { name: 'Continue as Raj Kumar' }))
  await page.keyboard.press('Enter')
  await tabTo(page, page.getByRole('link', { name: /^Transfer/ }).first())
  await page.keyboard.press('Enter')
  await tabTo(page, page.getByRole('button', { name: 'Prefill demo scenario' }))
  await page.keyboard.press('Enter')
  await tabTo(page, page.getByRole('button', { name: 'Review transfer' }))
  await page.keyboard.press('Enter')
  await tabTo(page, page.getByRole('button', { name: /^Send/ }))
  await page.keyboard.press('Enter')

  const sheet = page.getByRole('dialog', { name: 'Quick safety check' })
  await expect(sheet).toBeVisible()
  // quick replies are a radio group: arrow keys move between them
  await tabTo(page, sheet.getByRole('radio', { name: 'A government officer' }))
  await page.keyboard.press('Space')
  await page.keyboard.press('ArrowRight')
  await expect(sheet.getByRole('radio', { name: 'A job recruiter' })).toBeChecked()
  await tabTo(page, sheet.getByRole('button', { name: 'Check now' }))
  await page.keyboard.press('Enter')

  await expect(page.getByTestId('verdict-AMBER')).toBeVisible()
  await expect(page.getByRole('heading', { level: 1 })).toBeFocused()
  // every warning sign in the list can be reached and toggled
  const item = page.getByRole('button', { name: /Pay to earn/ })
  await tabTo(page, item)
  await page.keyboard.press('Enter')
  await expect(item).toHaveAttribute('aria-pressed', 'true')
  await tabTo(page, page.getByRole('button', { name: 'Pause for 24 hours' }))
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('outcome-paused')).toBeVisible()
})
