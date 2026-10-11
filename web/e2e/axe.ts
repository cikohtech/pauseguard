// One axe scan (WCAG 2.1 A + AA, every impact level) plus a screenshot for review.
import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

export async function scan(page: Page, screen: string) {
  await page.waitForTimeout(350) // let enter animations settle (axe reads computed colours)
  await page.screenshot({ path: `test-results/screens/${test.info().project.name}-${screen}.png` })
  const { violations } = await new AxeBuilder({ page })
    // Script-less sandboxed iframes are left out: axe can't be injected into them (injecting
    // hangs Playwright). The only one is the console's Google Search suggestions chip, Google's
    // own HTML; the console gives it a title.
    .exclude('iframe[sandbox]')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const report = violations.map((v) => `${v.impact} ${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(' ')).join(', ')})`)
  expect(report, `axe on "${screen}"`).toEqual([])
}
