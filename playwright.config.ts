import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { createServer, type AddressInfo } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { defineConfig } from '@playwright/test';

async function findFreePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = (server.address() as AddressInfo).port;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

const createdHere = !process.env.TELAR_E2E_DIR;
if (!process.env.TELAR_E2E_DIR) {
  const root = mkdtempSync(join(tmpdir(), 'telar-e2e-'));
  const vaultDir = join(root, 'vault');
  const configDir = join(root, 'config');
  mkdirSync(vaultDir, { recursive: true });
  mkdirSync(configDir, { recursive: true });
  writeFileSync(join(vaultDir, 'welcome.md'), '# Welcome\n\nInitial smoke content.\n');
  writeFileSync(join(vaultDir, 'second.md'), '# Second Note\n\nFindable via search palette.\n');
  process.env.TELAR_E2E_DIR = root;
}
if (!process.env.TELAR_E2E_PORT) {
  process.env.TELAR_E2E_PORT = String(await findFreePort());
}
if (createdHere) {
  const root = process.env.TELAR_E2E_DIR;
  process.on('exit', () => {
    rmSync(root, { recursive: true, force: true });
  });
}

const root = process.env.TELAR_E2E_DIR;
const port = process.env.TELAR_E2E_PORT;
const vaultDir = join(root, 'vault');
const configDir = join(root, 'config');
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  webServer: {
    command: `npm run build && uv run --project . python server.py --vault "${vaultDir}" --host 127.0.0.1 --port ${port} --idle-timeout 0`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...process.env,
      XDG_CONFIG_HOME: configDir,
    },
  },
});
