import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const BASE_URL = process.env.DEMO_BASE_URL ?? 'http://127.0.0.1:8080';
const OUTPUT_DIR = path.resolve(process.env.DEMO_OUTPUT_DIR ?? '.tmp/bi-dashboard-recording');
const FRAME_DIR = path.join(OUTPUT_DIR, 'frames');
const COMPANY_NAME = process.env.DEMO_BI_COMPANY ?? '비스텔리젼스';
const INSPECTION_COMPANY = process.env.DEMO_BI_INSPECTION_COMPANY ?? 'Bistelligence';
const RECOVERY_MODE = process.env.DEMO_BI_RECOVERY === '1';
const CHROME_PATH = process.env.CHROME_PATH
  ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

fs.rmSync(OUTPUT_DIR, { recursive: true, force: true });
fs.mkdirSync(FRAME_DIR, { recursive: true });

const browser = await chromium.launch({
  executablePath: CHROME_PATH,
  headless: true,
  args: ['--hide-scrollbars=false', '--force-device-scale-factor=1', '--disable-gpu-vsync'],
});
const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 1,
  reducedMotion: 'no-preference',
});
const page = await context.newPage();

await page.addInitScript(() => {
  const installDemoCursor = () => {
    if (document.querySelector('[data-demo-cursor]')) return;
    const cursor = document.createElement('div');
    cursor.dataset.demoCursor = 'true';
    Object.assign(cursor.style, {
      position: 'fixed', left: '0', top: '0', width: '20px', height: '20px',
      borderRadius: '50%', background: 'rgba(255,255,255,.96)',
      border: '2px solid #087f4f', boxShadow: '0 2px 9px rgba(10,60,42,.28)',
      transform: 'translate(-50%, -50%)', pointerEvents: 'none', zIndex: '2147483646',
      transition: 'width 120ms ease, height 120ms ease, background 120ms ease',
    });
    document.documentElement.append(cursor);
    window.addEventListener('mousemove', (event) => {
      cursor.style.left = `${event.clientX}px`;
      cursor.style.top = `${event.clientY}px`;
    }, { passive: true });
    window.addEventListener('mousedown', (event) => {
      cursor.style.width = '15px';
      cursor.style.height = '15px';
      cursor.style.background = '#b9f6d5';
      const ring = document.createElement('div');
      Object.assign(ring.style, {
        position: 'fixed', left: `${event.clientX}px`, top: `${event.clientY}px`,
        width: '18px', height: '18px', borderRadius: '50%',
        border: '3px solid rgba(8,127,79,.72)',
        transform: 'translate(-50%, -50%) scale(.5)', opacity: '1',
        transition: 'transform 500ms cubic-bezier(.2,.8,.2,1), opacity 500ms ease',
        pointerEvents: 'none', zIndex: '2147483645',
      });
      document.documentElement.append(ring);
      requestAnimationFrame(() => {
        ring.style.transform = 'translate(-50%, -50%) scale(3.5)';
        ring.style.opacity = '0';
      });
      setTimeout(() => ring.remove(), 550);
    }, { passive: true });
    window.addEventListener('mouseup', () => {
      cursor.style.width = '20px';
      cursor.style.height = '20px';
      cursor.style.background = 'rgba(255,255,255,.96)';
    }, { passive: true });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installDemoCursor, { once: true });
  } else {
    installDemoCursor();
  }
});

await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'domcontentloaded' });
if (process.env.DEMO_DEBUG === '1') {
  console.log(JSON.stringify({
    url: page.url(),
    title: await page.title(),
    body: (await page.locator('body').innerText()).slice(0, 1000),
  }, null, 2));
}
await page.locator('.bi-page').waitFor({ state: 'visible', timeout: 30000 });
await page.locator('.bi-card').first().waitFor({ state: 'visible', timeout: 60000 });
await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'smooth'; });

if (RECOVERY_MODE) {
  await page.getByRole('button', { name: '기업 선택', exact: true }).click();
  await page.getByRole('option', { name: INSPECTION_COMPANY, exact: true }).click();
  await page.locator('#bi-page-title').filter({ hasText: INSPECTION_COMPANY }).waitFor({
    state: 'visible', timeout: 60000,
  });
  await page.locator('.bi-card').first().waitFor({ state: 'visible', timeout: 60000 });
}

const cdp = await context.newCDPSession(page);
const frames = [];
const actions = [];
const fastForward = [];
let frameIndex = 0;
const startedAt = Date.now();

cdp.on('Page.screencastFrame', async (event) => {
  const fileName = `${String(frameIndex).padStart(5, '0')}.jpg`;
  fs.writeFileSync(path.join(FRAME_DIR, fileName), Buffer.from(event.data, 'base64'));
  frames.push({ file: fileName, t: (Date.now() - startedAt) / 1000 });
  frameIndex += 1;
  await cdp.send('Page.screencastFrameAck', { sessionId: event.sessionId });
});
await cdp.send('Page.startScreencast', {
  format: 'jpeg', quality: 94, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1,
});

const pause = (milliseconds) => page.waitForTimeout(milliseconds);
const now = () => (Date.now() - startedAt) / 1000;

async function moveTo(locator, steps = 30) {
  await locator.waitFor({ state: 'visible', timeout: 15000 });
  const box = await locator.boundingBox();
  if (!box) throw new Error('Element has no bounding box');
  const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(point.x, point.y, { steps });
  return point;
}

async function click(locator, label, options = {}) {
  const point = await moveTo(locator, options.steps ?? 30);
  await pause(options.preDelay ?? 170);
  actions.push({
    type: 'click', label, x: Math.round(point.x), y: Math.round(point.y),
    t: now(), zoom: options.zoom ?? 1.3,
  });
  await page.mouse.down();
  await pause(90);
  await page.mouse.up();
  await pause(options.postDelay ?? 700);
  return point;
}

async function focus(locator, label, zoom = 1.55, hold = 1550) {
  await locator.evaluate((element) => {
    element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
  });
  await pause(700);
  const point = await moveTo(locator, 34);
  actions.push({ type: 'focus', label, x: point.x, y: point.y, t: now(), zoom });
  await pause(hold);
}

await page.mouse.move(1180, 590, { steps: 20 });
actions.push({ type: 'focus', label: 'BI 대시보드', x: 1180, y: 520, t: now(), zoom: 1.08 });
await pause(1000);

if (!RECOVERY_MODE) {
  const addSnapshotButton = page.getByRole('button', { name: '기업 스냅샷 추가', exact: true });
  await click(addSnapshotButton, '기업 스냅샷 추가', { zoom: 1.28, postDelay: 550 });
  const candidate = page.getByRole('option', { name: new RegExp(`^${COMPANY_NAME}`) });
  await click(candidate, `${COMPANY_NAME} 선택`, { zoom: 1.38, postDelay: 500 });

  const createButton = page.getByRole('button', { name: '선택 기업 생성', exact: true });
  const generationStart = now();
  await click(createButton, '선택 기업 생성', { zoom: 1.38, postDelay: 250 });
  await page.waitForFunction(
    (companyName) => {
      const title = document.querySelector('#bi-page-title');
      const dialog = document.querySelector('#bi-snapshot-manager-dialog');
      return !dialog && title?.textContent?.includes(companyName);
    },
    COMPANY_NAME,
    { timeout: 240000 },
  );
  const generationEnd = now();
  if (generationEnd - generationStart > 1.8) {
    fastForward.push({
      label: 'BI 스냅샷 생성', start: generationStart + 0.5,
      end: generationEnd - 0.5, target_duration: 1.4,
    });
  }
  await page.locator('.bi-card').first().waitFor({ state: 'visible', timeout: 60000 });
}

await focus(
  page.locator('.bi-header'),
  `${RECOVERY_MODE ? INSPECTION_COMPANY : COMPANY_NAME} 스냅샷 생성 완료`,
  1.22,
  1200,
);

await focus(page.locator('[data-card-id="revenue_growth"]'), '매출 및 성장 카드', 1.72, 1700);
await focus(page.locator('[data-card-id="profitability"]'), '수익성 카드', 1.72, 1700);
await focus(page.locator('[data-card-id="cash_flow"]'), '현금흐름 카드', 1.72, 1700);

await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
await pause(800);
const cardLibraryButton = page.getByRole('button', { name: /카드 추가/ });
await click(cardLibraryButton, '카드 추가', { zoom: 1.3, postDelay: 450 });
const cardDialog = page.getByRole('dialog', { name: '카드 추가' });
await focus(cardDialog, '재무 체력 히트맵 선택', 1.4, 900);
await click(cardDialog.getByRole('button', { name: '추가', exact: true }), '히트맵 추가', {
  zoom: 1.42, postDelay: 550,
});
await click(page.getByRole('button', { name: '카드 목록 닫기' }), '카드 목록 닫기', {
  zoom: 1.3, postDelay: 450,
});
await page.locator('[data-card-id="financial_health_heatmap"]').waitFor({ state: 'visible', timeout: 15000 });

await focus(page.locator('[data-card-id="stability"]'), '재무 안정성 카드', 1.68, 1700);
await focus(page.locator('[data-card-id="financial_scale"]'), '재무 규모 카드', 1.68, 1700);
await focus(
  page.locator('[data-card-id="financial_health_heatmap"]'),
  '재무 체력 히트맵',
  1.5,
  2600,
);

await cdp.send('Page.stopScreencast');
await pause(250);
fs.writeFileSync(
  path.join(OUTPUT_DIR, 'recording.json'),
  JSON.stringify({
    width: 1920,
    height: 1080,
    camera_mode: 'track',
    frame_sampling: 'nearest',
    started_at: new Date(startedAt).toISOString(),
    duration: now(),
    frames,
    actions,
    fast_forward: fastForward,
    company: RECOVERY_MODE ? INSPECTION_COMPANY : COMPANY_NAME,
    recovery_mode: RECOVERY_MODE,
  }, null, 2),
);

await context.close();
await browser.close();
console.log(JSON.stringify({
  frameCount: frames.length,
  actionCount: actions.length,
  fastForwardCount: fastForward.length,
  duration: now(),
  company: RECOVERY_MODE ? INSPECTION_COMPANY : COMPANY_NAME,
  recoveryMode: RECOVERY_MODE,
}, null, 2));
