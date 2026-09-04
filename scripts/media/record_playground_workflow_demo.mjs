import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const BASE_URL = process.env.DEMO_BASE_URL ?? 'http://127.0.0.1:8080';
const OUTPUT_DIR = path.resolve(process.env.DEMO_OUTPUT_DIR ?? '.tmp/playground-workflow-recording');
const FRAME_DIR = path.join(OUTPUT_DIR, 'frames');
const CHROME_PATH = process.env.CHROME_PATH
  ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const QUERY = 'IBM의 현재 Total Enterprise Value(TEV)는?';

const NODE_ORDER = [
  'query',
  'data-scope',
  'decompose',
  'embed-query',
  'keyword',
  'dense',
  'fuse',
  'expand-context',
  'read',
];
const NODE_LABELS = {
  query: 'Query Input',
  'data-scope': 'PostgreSQL Data Scope',
  decompose: 'Scope-aware Query Decomposer',
  'embed-query': 'Query Embedder',
  keyword: 'Native Keyword Retriever',
  dense: 'pgvector Retriever',
  fuse: 'RRF Fusion',
  'expand-context': 'Context Expander',
  read: 'LLM Reader Answer',
};
const CAMERA_STAGE = {
  query: 0,
  'data-scope': 1,
  decompose: 2,
  'embed-query': 3,
  keyword: 4,
  dense: 4,
  fuse: 5,
  'expand-context': 6,
  read: 7,
};

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
const apiRequests = [];
page.on('request', (request) => {
  if (!request.url().includes('/api/')) return;
  apiRequests.push({
    method: request.method(),
    url: request.url(),
    post_data: request.postData(),
  });
});

// Hide prior runs from this isolated demo session so the UI cannot reuse the
// last completed query while still leaving the shared server history intact.
await page.route(/\/api\/(?:v1\/)?runs\?workflow_id=/, async (route) => {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ runs: [] }),
  });
});

// Force only this demo run to execute every module so RUNNING transitions are
// observable. Playwright recalculates Content-Length for the rewritten body.
await page.route(/\/api\/(?:v1\/)?workflows\/[^/]+\/runs$/, async (route) => {
  const request = route.request();
  const payload = request.postDataJSON();
  await route.continue({
    postData: JSON.stringify({ ...payload, use_cache: false }),
  });
});

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

await page.goto(`${BASE_URL}/playground`, { waitUntil: 'domcontentloaded' });
await page.getByRole('heading', { name: 'RAG 워크플로 플레이그라운드' }).waitFor({
  state: 'visible',
  timeout: 30000,
});

const workflowSelect = page.getByLabel('활성 워크플로 선택');
await workflowSelect.selectOption({ index: 0 });
await page.locator('.react-flow__node[data-id="read"]').waitFor({ state: 'visible', timeout: 30000 });
await page.waitForFunction(
  () => {
    const runButton = [...document.querySelectorAll('button')]
      .find((element) => element.textContent?.trim() === '자동 실행');
    return runButton instanceof HTMLButtonElement && !runButton.disabled;
  },
  undefined,
  { timeout: 30000 },
);

// A fresh browser context loads the standard graph without execution results.
// The header reset action intentionally clears the canvas, so it must not be
// used as a pre-recording cleanup step.
const closePalette = page.getByRole('button', { name: '모듈 패널 닫기', exact: true }).first();
if (await closePalette.isVisible().catch(() => false)) {
  await closePalette.click();
  await page.waitForTimeout(350);
}
const fitView = page.getByRole('button', { name: 'Fit View', exact: true });
if (await fitView.isVisible().catch(() => false)) {
  await fitView.click();
  await page.waitForTimeout(450);
}

const cdp = await context.newCDPSession(page);
const frames = [];
const actions = [];
const fastForward = [];
const stateEvents = [];
let frameIndex = 0;
const startedAt = Date.now();

const elapsed = () => (Date.now() - startedAt) / 1000;

cdp.on('Page.screencastFrame', async (event) => {
  const fileName = `${String(frameIndex).padStart(5, '0')}.jpg`;
  fs.writeFileSync(path.join(FRAME_DIR, fileName), Buffer.from(event.data, 'base64'));
  frames.push({ file: fileName, t: elapsed() });
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

function clampTarget(target) {
  return {
    x: Math.max(90, Math.min(1830, target.x)),
    y: Math.max(130, Math.min(990, target.y)),
  };
}

async function locatorCenter(locator) {
  await locator.waitFor({ state: 'visible', timeout: 12000 });
  const box = await locator.boundingBox();
  if (!box) throw new Error('Element has no bounding box');
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

async function focus(locator, label, options = {}) {
  const target = await locatorCenter(locator);
  await page.mouse.move(target.x, target.y, { steps: options.steps ?? 20 });
  actions.push({
    type: options.type ?? 'focus',
    label,
    x: Math.round(target.x),
    y: Math.round(target.y),
    t: elapsed(),
    zoom: options.zoom ?? 2.05,
  });
  await pause(options.postDelay ?? 220);
  return target;
}

async function click(locator, label, options = {}) {
  const target = await locatorCenter(locator);
  await page.mouse.move(target.x, target.y, { steps: options.steps ?? 24 });
  await pause(options.preDelay ?? 170);
  actions.push({
    type: 'click',
    label,
    x: Math.round(target.x),
    y: Math.round(target.y),
    t: elapsed(),
    zoom: options.zoom ?? 1.35,
  });
  await page.mouse.down();
  await pause(90);
  await page.mouse.up();
  await pause(options.postDelay ?? 420);
  return target;
}

async function readNodeStates() {
  return page.locator('.react-flow__node[data-id]').evaluateAll((elements) => Object.fromEntries(
    elements.map((element) => {
      const shell = element.querySelector('.flow-node');
      const rect = element.getBoundingClientRect();
      return [element.getAttribute('data-id'), {
        state: shell?.getAttribute('data-state') ?? 'idle',
        x: rect.x + rect.width / 2,
        y: rect.y + rect.height / 2,
        width: rect.width,
        height: rect.height,
      }];
    }),
  ));
}

let furthestCameraStage = -1;

async function focusNodeEvent(nodeId, state, node, nodes) {
  const label = `${NODE_LABELS[nodeId] ?? nodeId} ${state === 'active' ? '실행 중' : '완료'}`;
  const stateEventTime = elapsed();
  stateEvents.push({ node_id: nodeId, state, t: stateEventTime });

  const stage = CAMERA_STAGE[nodeId] ?? furthestCameraStage + 1;
  // A stage remains in view until the next stage starts. Completion events
  // update the node UI in place and must not pull the camera back to a branch
  // that finished late.
  if (stage <= furthestCameraStage) return;
  furthestCameraStage = stage;

  const retrievalNodes = stage === CAMERA_STAGE.keyword
    ? ['keyword', 'dense'].map((id) => nodes[id]).filter(Boolean)
    : [];
  const cameraNode = retrievalNodes.length > 0
    ? {
        x: retrievalNodes.reduce((sum, item) => sum + item.x, 0) / retrievalNodes.length,
        y: retrievalNodes.reduce((sum, item) => sum + item.y, 0) / retrievalNodes.length,
      }
    : node;
  const target = clampTarget({ x: cameraNode.x, y: cameraNode.y });
  await page.mouse.move(target.x, target.y, { steps: 18 });
  const cameraTime = elapsed();
  actions.push({
    type: state === 'active' ? 'module-running' : 'module-complete',
    label,
    x: Math.round(target.x),
    y: Math.round(target.y),
    t: cameraTime,
    zoom: stage === CAMERA_STAGE.keyword ? 1.62 : nodeId === 'read' ? 2.35 : 2.12,
    camera_stage: stage,
  });
  await pause(120);
}

await page.mouse.move(960, 440);
await pause(650);
await focus(workflowSelect, '첫 번째 기본 워크플로', { zoom: 1.16, postDelay: 480 });

const queryInput = page.locator('#playground-query-input');
await click(queryInput, '질문 입력', { zoom: 1.55, postDelay: 180 });
await queryInput.fill('');
for (const character of QUERY) {
  await page.keyboard.insertText(character);
  await pause(48);
}
await page.keyboard.press('Tab');
await page.waitForFunction(
  (expected) => document.querySelector('#playground-query-input')?.value === expected,
  QUERY,
  { timeout: 3000 },
);
await pause(420);
const queryTarget = await locatorCenter(queryInput);
actions.push({
  type: 'focus',
  label: QUERY,
  x: Math.round(queryTarget.x),
  y: Math.round(queryTarget.y),
  t: elapsed(),
  zoom: 1.62,
});
await pause(700);

const runButton = page.getByRole('button', { name: '자동 실행', exact: true });
await click(runButton, '전체 실행', { zoom: 1.42, postDelay: 120 });
const executionStart = elapsed();

const previousStates = Object.fromEntries(NODE_ORDER.map((nodeId) => [nodeId, 'idle']));
const runningStartedAt = {};
const deadline = Date.now() + 180000;
let readerFinished = false;

while (Date.now() < deadline) {
  const nodes = await readNodeStates();
  for (const nodeId of NODE_ORDER) {
    const node = nodes[nodeId];
    if (!node) continue;
    const prior = previousStates[nodeId];
    if (node.state === prior) continue;
    previousStates[nodeId] = node.state;

    if (node.state === 'active') {
      runningStartedAt[nodeId] = elapsed();
      await focusNodeEvent(nodeId, 'active', node, nodes);
    }
    if (node.state === 'done') {
      await focusNodeEvent(nodeId, 'done', node, nodes);
      const runStart = runningStartedAt[nodeId];
      const runEnd = elapsed();
      if (typeof runStart === 'number' && runEnd - runStart > 0.65) {
        fastForward.push({
          label: `${NODE_LABELS[nodeId] ?? nodeId} 실행`,
          start: runStart,
          end: runEnd,
          target_duration: Math.min(1.55, Math.max(0.72, (runEnd - runStart) * 0.22)),
        });
      }
      if (nodeId === 'read') readerFinished = true;
    }
    if (node.state === 'failed') {
      throw new Error(`${NODE_LABELS[nodeId] ?? nodeId} execution failed`);
    }
  }

  if (readerFinished && await page.locator('.react-flow__node[data-id="read"] .reader-markdown').isVisible().catch(() => false)) {
    break;
  }
  await pause(90);
}

if (!readerFinished) {
  throw new Error('Reader did not finish within 180 seconds');
}

const readerAnswer = page.locator('.react-flow__node[data-id="read"] .reader-markdown').first();
await readerAnswer.waitFor({ state: 'visible', timeout: 10000 });
const readerNode = page.locator('.react-flow__node[data-id="read"]').first();
const readerBoxBeforeZoom = await readerNode.boundingBox();
const readerZoomTarget = clampTarget(readerBoxBeforeZoom
  ? {
      x: readerBoxBeforeZoom.x + readerBoxBeforeZoom.width / 2,
      y: readerBoxBeforeZoom.y + readerBoxBeforeZoom.height / 2,
    }
  : { x: 1500, y: 560 });
await page.mouse.move(readerZoomTarget.x, readerZoomTarget.y, { steps: 26 });
actions.push({
  type: 'canvas-zoom',
  label: 'Reader 모듈 확대',
  x: Math.round(readerZoomTarget.x),
  y: Math.round(readerZoomTarget.y),
  t: elapsed(),
  zoom: 2.15,
});

// Zoom React Flow itself before the final camera move. Enlarging the actual
// DOM keeps Reader text crisp; a large post-process crop only magnifies the
// small fit-view raster and makes the answer look soft.
for (let step = 0; step < 8; step += 1) {
  await page.mouse.wheel(0, -420);
  await pause(120);
}
await pause(420);

// The Reader lives at the right edge of the default DAG. Pan the enlarged
// canvas so the complete module—not a clipped half—sits in the viewport.
const readerBoxAfterZoom = await readerNode.boundingBox();
if (readerBoxAfterZoom) {
  const readerCenterX = readerBoxAfterZoom.x + readerBoxAfterZoom.width / 2;
  const readerCenterY = readerBoxAfterZoom.y + readerBoxAfterZoom.height / 2;
  const panDeltaX = Math.max(-760, Math.min(760, 1020 - readerCenterX));
  const panDeltaY = Math.max(-220, Math.min(220, 560 - readerCenterY));
  const panStart = { x: 960, y: 900 };
  await page.mouse.move(panStart.x, panStart.y, { steps: 18 });
  await page.mouse.down();
  await page.mouse.move(panStart.x + panDeltaX, panStart.y + panDeltaY, { steps: 34 });
  await page.mouse.up();
  await pause(520);
}

const answerBox = await readerAnswer.boundingBox();
const answerTarget = clampTarget(answerBox
  ? {
      x: answerBox.x + answerBox.width / 2,
      y: answerBox.y + Math.min(answerBox.height / 2, 190),
    }
  : { x: 1500, y: 560 });
const centeredReaderBox = await readerNode.boundingBox();
const cursorRestTarget = clampTarget(centeredReaderBox
  ? {
      x: centeredReaderBox.x + centeredReaderBox.width - 38,
      y: centeredReaderBox.y + 38,
    }
  : { x: 1370, y: 350 });
// Leave the visible demo cursor in the Reader header so it never obscures the
// enlarged answer text while the camera remains centered on the answer.
await page.mouse.move(cursorRestTarget.x, cursorRestTarget.y, { steps: 26 });
const answerFocusStart = elapsed();
actions.push({
  type: 'final-answer',
  label: 'Reader 최종 답변',
  x: Math.round(answerTarget.x),
  y: Math.round(answerTarget.y),
  t: answerFocusStart,
  zoom: 2.35,
});
await pause(4200);
fastForward.push({
  label: 'Reader 최종 답변 확인',
  start: answerFocusStart,
  end: elapsed(),
  target_duration: 3.6,
});

await cdp.send('Page.stopScreencast');
await pause(250);

const recording = {
  width: 1920,
  height: 1080,
  camera_mode: 'track',
  frame_sampling: 'nearest',
  query: QUERY,
  workflow_id: 'rag_query',
  started_at: new Date(startedAt).toISOString(),
  duration: elapsed(),
  execution_start: executionStart,
  frames,
  actions,
  state_events: stateEvents,
  api_requests: apiRequests,
  fast_forward: fastForward,
};
fs.writeFileSync(path.join(OUTPUT_DIR, 'recording.json'), JSON.stringify(recording, null, 2));

await context.close();
await browser.close();

console.log(JSON.stringify({
  frameCount: frames.length,
  actionCount: actions.length,
  stateEventCount: stateEvents.length,
  duration: recording.duration,
  query: QUERY,
}, null, 2));
