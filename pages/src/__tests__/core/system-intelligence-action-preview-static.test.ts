/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const testDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(testDir, '../../../..');
const previewScript = readFileSync(
  resolve(repoRoot, 'src/apps/system_intelligence/static/system_intelligence/js/action-preview.js'),
  'utf8',
);

const FRONTEND = 'https://frontend.example';
const NONCE = 'nonce-frame-one';
const OTHER_NONCE = 'nonce-frame-two';
const block = {block_type: 'rich_text', sort_order: 0, data: {body_html: '<p>New Copy</p>'}};

type Frame = {nonce: string; dataSrc: string};

const listeners: Array<[string, EventListenerOrEventListenerObject]> = [];

// Mirrors system_intelligence_action_preview.html: one data-src frame per block, the block
// payload in a json_script, then action-preview.js.
function installPreview(frames: Frame[], payloadNonces = frames.map((frame) => frame.nonce)) {
  const data = document.createElement('script');
  data.id = 'si-action-preview-data';
  data.type = 'application/json';
  data.textContent = JSON.stringify({
    pageCssClass: 'page-about',
    blocks: payloadNonces.map((nonce) => ({nonce, block})),
  });
  document.body.append(data);

  const elements = frames.map(({nonce, dataSrc}) => {
    const iframe = document.createElement('iframe');
    iframe.className = 'si-action-preview-frame';
    iframe.setAttribute('data-src', dataSrc);
    iframe.setAttribute('data-preview-nonce', nonce);
    document.body.append(iframe);
    return iframe;
  });
  window.eval(previewScript);
  return elements;
}

function fromFrame(iframe: HTMLIFrameElement, data: unknown, origin = FRONTEND) {
  window.dispatchEvent(new MessageEvent('message', {data, origin, source: iframe.contentWindow}));
}

describe('System Intelligence action preview frames', () => {
  beforeEach(() => {
    const addEventListener = window.addEventListener.bind(window);
    vi.spyOn(window, 'addEventListener').mockImplementation((type, listener, options) => {
      listeners.push([type, listener]);
      addEventListener(type, listener, options);
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    listeners.splice(0).forEach(([type, listener]) => window.removeEventListener(type, listener));
    document.body.replaceChildren();
  });

  it('loads the frame from its /_block-preview URL and posts the block once it is ready', () => {
    const [frame] = installPreview([{nonce: NONCE, dataSrc: `${FRONTEND}/_block-preview?nonce=${NONCE}`}]);
    const postMessage = vi.spyOn(frame.contentWindow!, 'postMessage');

    expect(frame.getAttribute('src')).toBe(`${FRONTEND}/_block-preview?nonce=${NONCE}`);

    fromFrame(frame, {type: 'cms-block-preview-ready', nonce: NONCE});
    expect(postMessage).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledWith(
      {type: 'cms-block-preview', nonce: NONCE, block, pageCssClass: 'page-about'},
      FRONTEND,
    );

    fromFrame(frame, {type: 'cms-block-preview-resize', nonce: NONCE, height: 250.2});
    expect(frame.style.height).toBe('251px');
    fromFrame(frame, {type: 'cms-block-preview-resize', nonce: NONCE, height: 99999});
    expect(frame.style.height).toBe('4000px');
  });

  it.each([
    ['an empty FRONTEND_URL (relative path)', `/_block-preview?nonce=${NONCE}`, window.location.origin],
    ['the local Vite dev server', `http://localhost:5173/_block-preview?nonce=${NONCE}`, 'http://localhost:5173'],
  ])('keeps previews working for %s', (_label, dataSrc, origin) => {
    const [frame] = installPreview([{nonce: NONCE, dataSrc}]);
    const postMessage = vi.spyOn(frame.contentWindow!, 'postMessage');

    expect(frame.src).toBe(`${origin}/_block-preview?nonce=${NONCE}`);
    fromFrame(frame, {type: 'cms-block-preview-ready', nonce: NONCE}, origin);
    expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({nonce: NONCE, block}), origin);
  });

  it('posts on load when the ready message never arrives', () => {
    vi.useFakeTimers();
    const [frame] = installPreview([{nonce: NONCE, dataSrc: `${FRONTEND}/_block-preview?nonce=${NONCE}`}]);
    const postMessage = vi.spyOn(frame.contentWindow!, 'postMessage');

    frame.dispatchEvent(new Event('load'));
    vi.advanceTimersByTime(300);

    expect(postMessage).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({nonce: NONCE}), FRONTEND);
  });

  it.each([
    'javascript:alert(document.domain)',
    'JaVaScRiPt:alert(1)',
    '\u0001 java\tscr\nipt:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'vbscript:msgbox(1)',
    `blob:${FRONTEND}/0b1d6f3e-6a0e-4c43-9a62-0b8f1b1b7c11`,
    `${FRONTEND}/admin/?nonce=${NONCE}`,
    `${FRONTEND}/_block-preview/../admin/`,
    `${FRONTEND}/_block-preview-evil?nonce=${NONCE}`,
    `https://user:secret@frontend.example/_block-preview?nonce=${NONCE}`,
    'https://[frontend.example/_block-preview',
  ])('never loads or messages a frame whose data-src is %j', (dataSrc) => {
    const [bad, good] = installPreview([
      {nonce: NONCE, dataSrc},
      {nonce: OTHER_NONCE, dataSrc: `${FRONTEND}/_block-preview?nonce=${OTHER_NONCE}`},
    ]);
    const postMessage = vi.spyOn(bad.contentWindow!, 'postMessage');

    expect(bad.hasAttribute('src')).toBe(false);
    fromFrame(bad, {type: 'cms-block-preview-ready', nonce: NONCE});
    fromFrame(bad, {type: 'cms-block-preview-ready', nonce: NONCE}, window.location.origin);
    expect(postMessage).not.toHaveBeenCalled();
    // One rejected frame does not stop the other previews.
    expect(good.getAttribute('src')).toBe(`${FRONTEND}/_block-preview?nonce=${OTHER_NONCE}`);
  });

  it('decodes entity-escaped data-src text before validating it', () => {
    document.body.innerHTML =
      `<iframe class="si-action-preview-frame" data-src="&#106;avascript&#58;alert(1)"
         data-preview-nonce="${NONCE}"></iframe>`;
    const [frame] = Array.from(document.querySelectorAll('iframe'));
    const data = document.createElement('script');
    data.id = 'si-action-preview-data';
    data.type = 'application/json';
    data.textContent = JSON.stringify({blocks: [{nonce: NONCE, block}]});
    document.body.append(data);

    expect(frame.getAttribute('data-src')).toBe('javascript:alert(1)');
    window.eval(previewScript);

    expect(frame.hasAttribute('src')).toBe(false);
  });

  it('rebuilds the URL from the frame nonce instead of carrying data-src query or fragment text', () => {
    const nonce = 'a"><img src=x onerror=alert(1)>&next=1';
    const [frame] = installPreview([
      {nonce, dataSrc: `${FRONTEND}/_block-preview?nonce=other&next=javascript:alert(1)#"><svg onload=alert(1)>`},
    ]);

    const src = frame.getAttribute('src')!;
    expect(src).toBe(`${FRONTEND}/_block-preview?nonce=${encodeURIComponent(nonce)}`);
    const url = new URL(src);
    expect([...url.searchParams.keys()]).toEqual(['nonce']);
    expect(url.searchParams.get('nonce')).toBe(nonce);
    expect(url.hash).toBe('');
  });

  it('ignores messages from another origin, another window or another nonce', () => {
    const [frame] = installPreview([{nonce: NONCE, dataSrc: `${FRONTEND}/_block-preview?nonce=${NONCE}`}]);
    const postMessage = vi.spyOn(frame.contentWindow!, 'postMessage');

    fromFrame(frame, {type: 'cms-block-preview-ready', nonce: NONCE}, 'https://evil.example');
    window.dispatchEvent(
      new MessageEvent('message', {data: {type: 'cms-block-preview-ready', nonce: NONCE}, origin: FRONTEND, source: window}),
    );
    fromFrame(frame, {type: 'cms-block-preview-ready', nonce: OTHER_NONCE});
    fromFrame(frame, {type: 'cms-block-preview-resize', nonce: NONCE, height: 300}, 'https://evil.example');

    expect(postMessage).not.toHaveBeenCalled();
    expect(frame.style.height).toBe('');
  });

  it('skips frames whose nonce has no block in the payload', () => {
    const [frame] = installPreview([{nonce: NONCE, dataSrc: `${FRONTEND}/_block-preview?nonce=${NONCE}`}], [OTHER_NONCE]);

    expect(frame.hasAttribute('src')).toBe(false);
  });
});
