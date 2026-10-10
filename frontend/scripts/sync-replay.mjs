// Copies the backend's saved results into public/replay so Replay mode also works with the backend switched off.
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const from = join(here, '..', '..', 'backend', 'data', 'cached')
const to = join(here, '..', 'public', 'replay')

if (!existsSync(join(from, 'index.json'))) {
  console.error('No backend/data/cached/index.json found: nothing to sync.')
  process.exit(1)
}
rmSync(to, { recursive: true, force: true })
mkdirSync(to, { recursive: true })
const files = readdirSync(from).filter((f) => f.endsWith('.json'))
for (const f of files) copyFileSync(join(from, f), join(to, f))
console.log(`Synced ${files.length} files to public/replay`)
