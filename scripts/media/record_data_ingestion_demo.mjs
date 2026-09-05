import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const BASE_URL = process.env.DEMO_BASE_URL ?? 'http://127.0.0.1:8080';
const INPUT_FILE = path.resolve(
  process.env.DEMO_INPUT_FILE
    ?? 'data/source_files/SPG_Company_KeyStats_01_amesoft_rank_recalibrated.xlsx',
);
const UPLOAD_FILE_NAME = process.env.DEMO_UPLOAD_NAME
  ?? 'SPG_Company_KeyStats_01_amesoft_demo.xlsx';
const OUTPUT_DIR = path.resolve(
  process.env.DEMO_OUTPUT_DIR ?? '.tmp/data-ingestion-recording',
);
const FRAME_DIR = path.join(OUTPUT_DIR, 'frames');
const CHROME_PATH = process.env.CHROME_PATH
  ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const MAX_RUN_MS = Number(process.env.DEMO_MAX_RUN_MS ?? 12 * 60 * 1000);
const RECOVERY_INDEX_ID = process.env.DEMO_RECOVERY_INDEX_ID ?? '';

if (!fs.existsSync(INPUT_FILE)) {
  throw new Error(`Demo workbook does not exist: ${INPUT_FILE}`);
}

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

await page.goto(`${BASE_URL}/data-sources`, { waitUntil: 'domcontentloaded' });
await page.locator('.ds-tab-content').waitFor({ state: 'visible', timeout: 60000 });

const cdp = await context.newCDPSession(page);
const frames = [];
const actions = [];
const fastForward = [];
let frameIndex = 0;
const startedAt = Date.now();

const sourceTime = () => (Date.now() - startedAt) / 1000;
const pause = (milliseconds) => page.waitForTimeout(milliseconds);

cdp.on('Page.screencastFrame', async (event) => {
  const fileName = `${String(frameIndex).padStart(5, '0')}.jpg`;
  fs.writeFileSync(path.join(FRAME_DIR, fileName), Buffer.from(event.data, 'base64'));
  frames.push({ file: fileName, t: sourceTime() });
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

async function moveTo(locator, steps = 26) {
  await locator.waitFor({ state: 'visible', timeout: 30000 });
  const box = await locator.boundingBox();
  if (!box) throw new Error('Element has no bounding box');
  const target = {
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
  };
  await page.mouse.move(target.x, target.y, { steps });
  return target;
}

function rememberAction(type, label, target, zoom = 1.16) {
  actions.push({
    type,
    label,
    x: Math.round(target.x),
    y: Math.round(target.y),
    t: sourceTime(),
    zoom,
  });
}

async function click(locator, label, options = {}) {
  const target = await moveTo(locator, options.steps ?? 28);
  await pause(options.preDelay ?? 180);
  rememberAction('click', label, target, options.zoom ?? 1.2);
  await page.mouse.down();
  await pause(90);
  await page.mouse.up();
  await pause(options.postDelay ?? 650);
}

async function focus(locator, label, zoom = 1.15, dwellMs = 650) {
  await locator.scrollIntoViewIfNeeded();
  await pause(260);
  const target = await moveTo(locator, 30);
  rememberAction('focus', label, target, zoom);
  await pause(dwellMs);
  return sourceTime();
}

function compressGap(label, start, end, targetDuration = 0.85) {
  if (end - start < 1.8) return;
  fastForward.push({
    label,
    start: start + 0.55,
    end: end - 0.40,
    target_duration: targetDuration,
  });
}

async function captureLunaInspector() {
  const lunaInspectButton = page.getByRole('button', {
    name: 'Luna 구조 돋보기 검사',
    exact: true,
  });
  await click(lunaInspectButton, 'Luna VLM 구조화 분석 열기', {
    zoom: 1.22,
    postDelay: 500,
  });

  const inspector = page.getByRole('dialog');
  await inspector.waitFor({ state: 'visible', timeout: 30000 });
  await page.waitForFunction(
    () => {
      const image = document.querySelector('.spreadsheet-result-stage img');
      return image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0;
    },
    undefined,
    { timeout: 60000 },
  );

  await focus(
    page.locator('.spreadsheet-result-toolbar').first(),
    '첫 번째 시트 구조 분석 결과',
    1.10,
    850,
  );

  const zoomInButton = page.getByRole('button', { name: '확대', exact: true });
  for (let level = 1; level <= 3; level += 1) {
    await click(zoomInButton, `첫 번째 시트 확대 ${level}/3`, {
      zoom: 1.14 + level * 0.025,
      preDelay: 130,
      postDelay: 430,
    });
  }

  const firstDetectedRegion = page.locator('.spreadsheet-result-box').first();
  if (await firstDetectedRegion.isVisible().catch(() => false)) {
    await click(firstDetectedRegion, '감지된 구조 영역 확인', {
      zoom: 1.24,
      postDelay: 750,
    });
  }

  await focus(
    page.getByRole('region', { name: '스프레드시트 결과 캔버스 · 드래그하여 이동' }),
    '확대된 첫 번째 시트 구조화 결과',
    1.27,
    2800,
  );
}

async function saveRecording() {
  await cdp.send('Page.stopScreencast');
  await pause(250);

  const recording = {
    width: 1920,
    height: 1080,
    camera_mode: 'track',
    frame_sampling: 'nearest',
    started_at: new Date(startedAt).toISOString(),
    duration: sourceTime(),
    frames,
    actions,
    fast_forward: fastForward,
    source_file: UPLOAD_FILE_NAME,
  };

  fs.writeFileSync(
    path.join(OUTPUT_DIR, 'recording.json'),
    JSON.stringify(recording, null, 2),
  );

  await context.close();
  await browser.close();

  console.log(JSON.stringify({
    frameCount: frames.length,
    actionCount: actions.length,
    fastForwardCount: fastForward.length,
    duration: recording.duration,
    sourceFile: recording.source_file,
  }, null, 2));
}

if (RECOVERY_INDEX_ID) {
  await page.mouse.move(1430, 220);
  rememberAction('focus', '완료된 데이터 소스', { x: 1220, y: 360 }, 1.08);
  await pause(750);

  const row = page.locator('tbody tr').filter({ hasText: UPLOAD_FILE_NAME }).first();
  await row.waitFor({ state: 'visible', timeout: 120000 });
  await click(row.getByRole('button', { name: '모듈 로그', exact: true }), '완료된 모듈 로그 열기', {
    zoom: 1.20,
    postDelay: 450,
  });
  await page.locator('.ds-pipeline-tracker').waitFor({ state: 'visible', timeout: 60000 });

  const holdButton = page.getByRole('button', { name: '로그 계속 보기', exact: true });
  if (await holdButton.isVisible().catch(() => false)) {
    await click(holdButton, '완료 상태 계속 보기', { zoom: 1.2, postDelay: 350 });
  }

  await focus(page.locator('.ds-pipeline-header'), 'AmeSoft 적재 완료', 1.11, 650);
  const completedCards = page.locator('.ds-module-card');
  const completedCardCount = await completedCards.count();
  for (let index = 0; index < completedCardCount; index += 1) {
    const card = completedCards.nth(index);
    const label = await card.locator('.ds-module-card__title strong').innerText();
    await focus(card, `${label} 완료`, 1.15, 360);
  }

  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await pause(550);
  await focus(page.locator('.ds-pipeline-hud-card'), '적재 결과와 비용 확인', 1.17, 900);
  await captureLunaInspector();
  await saveRecording();
  process.exit(0);
}

await page.mouse.move(1430, 220);
rememberAction('focus', '데이터 소스', { x: 1220, y: 360 }, 1.08);
await pause(900);

const createButton = page.getByRole('button', { name: '새 엑셀 인덱싱', exact: true });
await click(createButton, '새 엑셀 인덱싱', { zoom: 1.22, postDelay: 500 });

const fileInput = page.locator('input[type="file"]');
const dropzone = page.getByRole('button', { name: '인덱싱할 엑셀 파일 선택' });
await focus(dropzone, '엑셀 워크북 선택', 1.24, 350);
await fileInput.setInputFiles({
  name: UPLOAD_FILE_NAME,
  mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  buffer: fs.readFileSync(INPUT_FILE),
});
await pause(800);

const selectedFile = page.getByText(UPLOAD_FILE_NAME, { exact: true });
await focus(selectedFile, 'AmeSoft 워크북 선택 완료', 1.25, 650);

const modelSelect = page.getByLabel('임베딩 모델');
await click(modelSelect, '임베딩 모델 선택', { zoom: 1.22, postDelay: 180 });
await modelSelect.selectOption('text-embedding-3-large');
await pause(520);

const startButton = page.getByRole('button', { name: '인덱싱 시작', exact: true });
await click(startButton, '인덱싱 시작', { zoom: 1.25, postDelay: 260 });

const uploadStartedAt = sourceTime();
const tracker = page.locator('.ds-pipeline-tracker');
const uploadError = page.locator('.ds-page > .ds-error-alert');
const trackerDeadline = Date.now() + 120000;
while (Date.now() < trackerDeadline && !(await tracker.isVisible().catch(() => false))) {
  if (await uploadError.isVisible().catch(() => false)) {
    throw new Error(`Upload failed: ${await uploadError.innerText()}`);
  }
  await pause(250);
}
if (!(await tracker.isVisible().catch(() => false))) {
  throw new Error('Pipeline tracker did not open within 120000ms');
}
compressGap('파일 업로드와 작업 생성', uploadStartedAt, sourceTime(), 0.9);

await focus(page.locator('.ds-pipeline-header'), '파이프라인 실시간 모니터', 1.10, 650);

let lastStageKey = '';
let lastStageStartedAt = sourceTime();
let lastStageLabel = '작업 큐 대기';
const runDeadline = Date.now() + MAX_RUN_MS;
let completed = false;

while (Date.now() < runDeadline) {
  const state = await page.evaluate(() => {
    const tracker = document.querySelector('.ds-pipeline-tracker');
    if (!tracker) return { terminal: 'missing' };
    const failure = tracker.querySelector('.ds-module-status-badge--failed');
    if (failure) {
      return { terminal: 'failed', message: failure.textContent?.trim() || '실행 실패' };
    }
    const completedBadge = Array.from(
      tracker.querySelectorAll('.ds-module-status-badge--done'),
    ).find((node) => node.textContent?.includes('적재 완료'));
    if (completedBadge) return { terminal: 'completed' };

    const cards = Array.from(tracker.querySelectorAll('.ds-module-card'));
    const runningIndex = cards.findIndex((card) => card.classList.contains('is-running'));
    const running = runningIndex >= 0 ? cards[runningIndex] : null;
    const progress = running?.querySelector('[role="progressbar"]');
    const value = Number(progress?.getAttribute('aria-valuenow') || 0);
    const max = Number(progress?.getAttribute('aria-valuemax') || 0);
    const percent = max > 0 ? (value / max) * 100 : 0;
    const bucket = percent >= 99 ? 100 : percent >= 75 ? 75 : percent >= 50 ? 50 : percent >= 25 ? 25 : 0;
    const title = running?.querySelector('.ds-module-card__title strong')?.textContent?.trim()
      || tracker.querySelector('.ds-progress-header__title')?.textContent?.trim()
      || '실행 대기 중';
    return {
      terminal: 'running',
      runningIndex,
      title,
      bucket,
    };
  });

  if (state.terminal === 'failed') {
    throw new Error(`Ingestion failed: ${state.message}`);
  }
  if (state.terminal === 'completed') {
    compressGap(lastStageLabel, lastStageStartedAt, sourceTime(), 1.0);
    completed = true;
    break;
  }

  if (state.terminal === 'running') {
    const stageKey = `${state.runningIndex}:${state.bucket}`;
    if (stageKey !== lastStageKey) {
      const now = sourceTime();
      if (lastStageKey) {
        compressGap(lastStageLabel, lastStageStartedAt, now, state.bucket ? 0.85 : 1.05);
      }
      lastStageKey = stageKey;
      lastStageStartedAt = now;
      lastStageLabel = `${state.title} ${state.bucket}%`;

      if (state.runningIndex >= 0) {
        const card = page.locator('.ds-module-card').nth(state.runningIndex);
        await focus(
          card,
          `${state.title}${state.bucket ? ` · ${state.bucket}%` : ''}`,
          state.runningIndex >= 3 ? 1.18 : 1.14,
          520,
        );
      } else {
        await focus(page.locator('.ds-progress-container'), state.title, 1.12, 420);
      }
    }
  }

  await pause(320);
}

if (!completed) {
  throw new Error(`Ingestion did not finish within ${MAX_RUN_MS}ms`);
}

const autoReturnBanner = page.locator('.ds-auto-return-banner');
await autoReturnBanner.waitFor({ state: 'visible', timeout: 10000 });
const holdButton = page.getByRole('button', { name: '로그 계속 보기', exact: true });
if (await holdButton.isVisible().catch(() => false)) {
  await click(holdButton, '완료 상태 계속 보기', { zoom: 1.2, postDelay: 450 });
}

await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
await pause(600);
await focus(page.locator('.ds-progress-container'), '전체 모듈 파이프라인 완료', 1.16, 1250);
await focus(page.locator('.ds-pipeline-hud-card'), '적재 결과와 비용 확인', 1.17, 1150);

await captureLunaInspector();
await saveRecording();
