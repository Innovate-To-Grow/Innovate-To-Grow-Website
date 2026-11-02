/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {afterEach, describe, expect, it, vi} from 'vitest';

declare global {
  interface Window {
    ITGFooterPreview: {
      updatePreview: (iframe: HTMLIFrameElement, errorBox: HTMLElement, footerData: unknown) => void;
    };
  }
}

/**
 * The admin footer editor's preview script (src/apps/cms/static/layout/js/footer/editor/preview.js):
 * it frames the SPA's /_footer-preview at the template's data-preview-base and posts the footer content.
 */

const testDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(testDir, '../../../..');
const previewScript = readFileSync(
  resolve(repoRoot, 'src/apps/cms/static/layout/js/footer/editor/preview.js'),
  'utf8',
);

const UNSAFE_BASE_ERROR = 'Preview unavailable: the frontend URL is not an http(s) URL.';

function startPreview(base: string | null, footerData: unknown = {}) {
  document.body.innerHTML =
    '<div id="footer-preview-error"></div><iframe id="footer-preview-iframe" title="Footer preview"></iframe>';
  const iframe = document.getElementById('footer-preview-iframe') as HTMLIFrameElement;
  const errorBox = document.getElementById('footer-preview-error') as HTMLElement;
  if (base !== null) iframe.setAttribute('data-preview-base', base);
  window.eval(previewScript);
  window.ITGFooterPreview.updatePreview(iframe, errorBox, footerData);
  return {iframe, errorBox};
}

function frameNonce(iframe: HTMLIFrameElement) {
  return new URL(iframe.getAttribute('src') ?? '').searchParams.get('nonce') ?? '';
}

function readyMessage(iframe: HTMLIFrameElement, origin: string, nonce: string) {
  return new MessageEvent('message', {
    origin,
    source: iframe.contentWindow,
    data: {type: 'cms-footer-preview-ready', nonce},
  });
}

describe('footer editor preview frame', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    Reflect.deleteProperty(window, 'ITGFooterPreview');
    document.body.replaceChildren();
  });

  it.each([
    ['an https frontend', 'https://frontend.example', 'https://frontend.example/_footer-preview'],
    ['a trailing slash', 'https://frontend.example/', 'https://frontend.example/_footer-preview'],
    ['a path prefix', 'https://frontend.example/site//', 'https://frontend.example/site/_footer-preview'],
    ['an http dev server with a port', 'http://localhost:5173', 'http://localhost:5173/_footer-preview'],
    ['an empty base (same origin)', '', `${window.location.origin}/_footer-preview`],
    ['no base attribute (same origin)', null, `${window.location.origin}/_footer-preview`],
  ])('frames the footer preview for %s', (_label, base, expected) => {
    const {iframe, errorBox} = startPreview(base);

    const nonce = frameNonce(iframe);
    expect(nonce).toMatch(/^[0-9a-f]{36}$/);
    expect(iframe.getAttribute('src')).toBe(`${expected}?nonce=${nonce}`);
    expect(errorBox.textContent).toBe('');
  });

  it.each([
    'javascript:alert(document.domain)//',
    'JaVaScRiPt:alert(1)//',
    ' java\tscript:alert(1)//',
    'data:text/html,<script>alert(1)</script>',
    'vbscript:msgbox(1)',
    'blob:https://frontend.example/11111111-2222-4333-8444-555555555555',
  ])('never frames a non-http(s) base: %s', (base) => {
    const {iframe, errorBox} = startPreview(base, {copyright: '© 2026'});
    const postMessage = vi.spyOn(iframe.contentWindow as Window, 'postMessage');

    window.dispatchEvent(readyMessage(iframe, window.location.origin, ''));

    expect(iframe.hasAttribute('src')).toBe(false);
    expect(errorBox.textContent).toBe(UNSAFE_BASE_ERROR);
    expect(postMessage).not.toHaveBeenCalled();
  });

  it('keeps HTML metacharacters in the base percent-encoded inside the frame URL', () => {
    const {iframe} = startPreview('https://frontend.example/"><img src=x onerror=alert(1)>');

    const src = iframe.getAttribute('src') ?? '';
    expect(src.startsWith('https://frontend.example/')).toBe(true);
    expect(src).not.toMatch(/["'<>\s]/);
    expect(new URL(src).pathname.endsWith('/_footer-preview')).toBe(true);
  });

  it('drops credentials from the base instead of carrying them into the frame URL', () => {
    const {iframe} = startPreview('https://admin:secret@frontend.example');

    expect(iframe.getAttribute('src')).toBe(`https://frontend.example/_footer-preview?nonce=${frameNonce(iframe)}`);
  });

  it('posts the footer markup and styles unchanged to the framed frontend once it is ready', () => {
    const content = {
      contact_html: '<p style="color: #002856">Email <a href="mailto:i2g@example.edu">us</a></p>',
      columns: [{title: 'About', body_html: '<strong class="lead">Innovate</strong>', links: []}],
      copyright: '© 2026 Innovate To Grow',
    };
    const {iframe} = startPreview('https://frontend.example', content);
    const postMessage = vi.spyOn(iframe.contentWindow as Window, 'postMessage').mockImplementation(() => {});
    const nonce = frameNonce(iframe);

    // A message from another origin, or with the wrong nonce, is not the preview frame announcing itself.
    window.dispatchEvent(readyMessage(iframe, 'https://evil.example', nonce));
    window.dispatchEvent(readyMessage(iframe, 'https://frontend.example', 'wrong-nonce'));
    expect(postMessage).not.toHaveBeenCalled();

    window.dispatchEvent(readyMessage(iframe, 'https://frontend.example', nonce));

    expect(postMessage).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledWith({type: 'cms-footer-preview', nonce, content}, 'https://frontend.example');
  });
});
