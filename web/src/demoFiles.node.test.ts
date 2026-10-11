// Node-side check (typechecked by tsconfig.node.json): the demo evidence the web app serves from
// public/demo must stay byte-identical to data/demo, which `make demo-evidence` renders.
import { readFileSync } from 'node:fs'
import path from 'node:path'

test('the demo evidence served by the web app is the same as data/demo', () => {
  const root = path.resolve(import.meta.dirname, '../..')
  for (const file of ['tan_mas_chat.png', 'raj_job_chat.txt', 'aisyah_tenancy.pdf']) {
    const served = readFileSync(path.join(root, 'web/public/demo', file))
    const source = readFileSync(path.join(root, 'data/demo', file))
    expect(served.equals(source), file).toBe(true)
  }
})
