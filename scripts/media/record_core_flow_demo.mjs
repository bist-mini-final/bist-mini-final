import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const BASE_URL = process.env.DEMO_BASE_URL ?? 'http://127.0.0.1:8080';
const OUTPUT_DIR = path.resolve(process.env.DEMO_OUTPUT_DIR ?? '.tmp/core-flow-recording');
const FRAME_DIR = path.join(OUTPUT_DIR, 'frames');
const CHROME_PATH = process.env.CHROME_PATH
  ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

fs.rmSync(OUTPUT_DIR, { recursive: true, force: true });
fs.mkdirSync(FRAME_DIR, { recursive: true });

const browser = await chromium.launch({
  executablePath: CHROME_PATH,
  headless: true,
  args: [
    '--hide-scrollbars=false',
    '--force-device-scale-factor=1',
    '--disable-gpu-vsync',
  ],
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
      position: 'fixed',
      left: '0',
      top: '0',
      width: '20px',
      height: '20px',
      borderRadius: '50%',
      background: 'rgba(255,255,255,.96)',
      border: '2px solid #087f4f',
      boxShadow: '0 2px 9px rgba(10,60,42,.28)',
      transform: 'translate(-50%, -50%)',
      transition: 'width 120ms ease, height 120ms ease, background 120ms ease',
      pointerEvents: 'none',
      zIndex: '2147483646',
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
        position: 'fixed',
        left: `${event.clientX}px`,
        top: `${event.clientY}px`,
        width: '18px',
        height: '18px',
        borderRadius: '50%',
        border: '3px solid rgba(8,127,79,.72)',
        transform: 'translate(-50%, -50%) scale(.5)',
        opacity: '1',
        transition: 'transform 500ms cubic-bezier(.2,.8,.2,1), opacity 500ms ease',
        pointerEvents: 'none',
        zIndex: '2147483645',
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

// Start the loop on Data Sources. The recording ends on the completed chatbot
// answer, so the GIF loop now transitions directly from that answer to the
// first product workspace without flashing an empty/reset chatbot state.
await page.goto(`${BASE_URL}/data-sources`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(350);

const cdp = await context.newCDPSession(page);
const frames = [];
const actions = [];
const fastForward = [];
let frameIndex = 0;
const startedAt = Date.now();
let previousPoint = { x: 1180, y: 610 };

cdp.on('Page.screencastFrame', async (event) => {
  const fileName = `${String(frameIndex).padStart(5, '0')}.jpg`;
  fs.writeFileSync(path.join(FRAME_DIR, fileName), Buffer.from(event.data, 'base64'));
  frames.push({ file: fileName, t: (Date.now() - startedAt) / 1000 });
  frameIndex += 1;
  await cdp.send('Page.screencastFrameAck', { sessionId: event.sessionId });
});

await cdp.send('Page.startScreencast', {
  format: 'jpeg',
  quality: 94,
  maxWidth: 1920,
  maxHeight: 1080,
  everyNthFrame: 1,
});

const pause = (milliseconds) => page.waitForTimeout(milliseconds);

async function moveTo(locator, steps = 26) {
  await locator.waitFor({ state: 'visible', timeout: 12000 });
  const box = await locator.boundingBox();
  if (!box) throw new Error('Element has no bounding box');
  const target = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(target.x, target.y, { steps });
  previousPoint = target;
  return target;
}

async function click(locator, label, options = {}) {
  const target = await moveTo(locator, options.steps ?? 28);
  await pause(options.preDelay ?? 180);
  const action = {
    type: 'click',
    label,
    x: Math.round(target.x),
    y: Math.round(target.y),
    t: (Date.now() - startedAt) / 1000,
    zoom: options.zoom ?? 1.22,
  };
  actions.push(action);
  await page.mouse.down();
  await pause(90);
  await page.mouse.up();
  await pause(options.postDelay ?? 950);
  return action;
}

async function clickNav(name, expectedPath, settleDelay = 450) {
  const link = page.getByRole('link', { name, exact: true });
  await click(link, name, { zoom: 1.18, postDelay: 300 });
  await page.waitForURL((url) => url.pathname === expectedPath, { timeout: 12000 });
  await pause(settleDelay);
}

// Establish the cursor on the opening Data Sources scene.
await page.mouse.move(previousPoint.x, previousPoint.y);
await pause(350);

// 1. Inspect indexed workbooks.
const dataLoadingStart = (Date.now() - startedAt) / 1000;
await page.locator('.ds-tab-content').waitFor({ state: 'visible', timeout: 30000 });
await page.waitForFunction(
  () => document.querySelectorAll('.ds-tab-content table tbody tr').length > 0,
  undefined,
  { timeout: 30000 },
).catch(() => undefined);
const dataLoadingEnd = (Date.now() - startedAt) / 1000;
if (dataLoadingEnd - dataLoadingStart > 0.5) {
  fastForward.push({
    label: '데이터 소스 로딩',
    start: dataLoadingStart,
    end: dataLoadingEnd,
    target_duration: 0.95,
  });
}
await pause(1200);
const dataTable = page.locator('main table').first();
if (await dataTable.isVisible().catch(() => false)) {
  const box = await dataTable.boundingBox();
  if (box) {
    const target = { x: Math.min(box.x + box.width * 0.62, 1570), y: Math.min(box.y + 160, 720) };
    await page.mouse.move(target.x, target.y, { steps: 34 });
    previousPoint = target;
    actions.push({ type: 'focus', label: '인덱싱 컬렉션', x: target.x, y: target.y, t: (Date.now() - startedAt) / 1000, zoom: 1.14 });
    await pause(1050);
  }
}

// 2. Review the BI snapshot and its card layout.
await clickNav('BI 대시보드', '/dashboard');
const biLoadingStart = (Date.now() - startedAt) / 1000;
await page.locator('.bi-card').first().waitFor({ state: 'visible', timeout: 60000 });
const biLoadingEnd = (Date.now() - startedAt) / 1000;
if (biLoadingEnd - biLoadingStart > 0.5) {
  fastForward.push({
    label: 'BI 대시보드 로딩',
    start: biLoadingStart,
    end: biLoadingEnd,
    target_duration: 0.95,
  });
}
await pause(1100);
await page.mouse.move(1320, 760, { steps: 34 });
actions.push({ type: 'focus', label: 'BI 스냅샷', x: 1320, y: 650, t: (Date.now() - startedAt) / 1000, zoom: 1.12 });
await pause(700);
await page.mouse.wheel(0, 470);
await pause(1100);
await page.mouse.wheel(0, -470);
await pause(650);

// 3. Compare companies and open the detailed comparison state.
await clickNav('기업 비교', '/company-comparison');
const comparisonLoadingStart = (Date.now() - startedAt) / 1000;
await page.locator('.league-main-grid').waitFor({ state: 'visible', timeout: 60000 });
const comparisonLoadingEnd = (Date.now() - startedAt) / 1000;
if (comparisonLoadingEnd - comparisonLoadingStart > 0.5) {
  fastForward.push({
    label: '기업 비교 로딩',
    start: comparisonLoadingStart,
    end: comparisonLoadingEnd,
    target_duration: 0.95,
  });
}
await pause(1100);
const checkboxes = page.locator('main input[type="checkbox"]');
const checkboxCount = await checkboxes.count();
for (let index = 0; index < Math.min(2, checkboxCount); index += 1) {
  const checkbox = checkboxes.nth(index);
  if (await checkbox.isVisible().catch(() => false)) {
    await click(checkbox, `비교 기업 ${index + 1} 선택`, { zoom: 1.25, postDelay: 600 });
  }
}
await page.mouse.wheel(0, 540);
actions.push({ type: 'focus', label: '기업 비교 분석', x: 1190, y: 700, t: (Date.now() - startedAt) / 1000, zoom: 1.14 });
await pause(1250);
await page.mouse.wheel(0, -540);
await pause(500);

// 4. Return to chat and demonstrate a realistic financial question.
const newChatButton = page.getByRole('button', { name: '새 채팅', exact: true });
await click(newChatButton, '새 채팅', { zoom: 1.18, postDelay: 450 });
await page.waitForURL((url) => url.pathname === '/chatbot', { timeout: 12000 });
await pause(900);

const textarea = page.locator('textarea').first();
await click(textarea, '질문 입력', { zoom: 1.2, postDelay: 250 });
await textarea.fill('Nexora Labs의 매출 성장률과 수익성 변화를 알려줘.');
actions.push({ type: 'focus', label: '재무 질문 작성', x: previousPoint.x, y: previousPoint.y, t: (Date.now() - startedAt) / 1000, zoom: 1.16 });
await pause(650);

const sendButton = page.getByRole('button', { name: '질문하기', exact: true });
const answerLoadingStart = (Date.now() - startedAt) / 1000;
await click(sendButton, '질문하기', { zoom: 1.2, postDelay: 250 });
await page.waitForFunction(
  () => {
    const messages = document.querySelector('.chatbot-messages');
    const answer = document.querySelector('.chatbot-message--assistant .reader-markdown');
    return messages?.getAttribute('aria-busy') === 'false' && answer !== null;
  },
  undefined,
  { timeout: 120000 },
);
const answerLoadingEnd = (Date.now() - startedAt) / 1000;
fastForward.push({
  label: '챗봇 답변 생성',
  start: answerLoadingStart,
  end: answerLoadingEnd,
  target_duration: 1.25,
});

const answer = page.locator('.chatbot-message--assistant').last();
const answerBox = await answer.boundingBox();
const answerTarget = answerBox
  ? {
      x: Math.max(520, Math.min(1480, answerBox.x + answerBox.width / 2)),
      y: Math.max(260, Math.min(760, answerBox.y + Math.min(answerBox.height / 2, 280))),
    }
  : { x: 1120, y: 500 };
await page.mouse.move(answerTarget.x, answerTarget.y, { steps: 34 });
actions.push({ type: 'focus', label: '근거 기반 답변', x: answerTarget.x, y: answerTarget.y, t: (Date.now() - startedAt) / 1000, zoom: 1.14 });
await pause(2400);
await cdp.send('Page.stopScreencast');
await pause(250);

fs.writeFileSync(
  path.join(OUTPUT_DIR, 'recording.json'),
  JSON.stringify({
    width: 1920,
    height: 1080,
    frame_sampling: 'nearest',
    started_at: new Date(startedAt).toISOString(),
    duration: (Date.now() - startedAt) / 1000,
    frames,
    actions,
    fast_forward: fastForward,
  }, null, 2),
);

await context.close();
await browser.close();

console.log(JSON.stringify({ frameCount: frames.length, actionCount: actions.length, duration: (Date.now() - startedAt) / 1000 }, null, 2));
