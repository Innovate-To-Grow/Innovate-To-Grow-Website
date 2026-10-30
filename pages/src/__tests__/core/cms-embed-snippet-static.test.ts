/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

declare global {
  interface Window {
    ITGEmbedSnippet?: {buildEmbedSnippet: (embedUrl: string, slug: string) => string};
  }
}

const testDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(testDir, '../../../..');
const snippetScript = readFileSync(
  resolve(repoRoot, 'src/apps/cms/static/cms/js/cms-embed-widget/snippet.js'),
  'utf8',
);

const WIDGET_ORIGIN = 'https://i2g.example.edu';
const SLUG = 'projects-widget';

/** Pastes the admin's snippet into a partner page: the iframe, and its inline script run. */
function pasteSnippet(): HTMLIFrameElement {
  window.eval(snippetScript);
  const snippet = window.ITGEmbedSnippet!.buildEmbedSnippet(`${WIDGET_ORIGIN}/_embed/${SLUG}`, SLUG);
  document.body.innerHTML = snippet;
  window.eval(document.body.querySelector('script')!.textContent!);
  return document.body.querySelector('iframe')!;
}

const postResize = (data: Record<string, unknown>, origin = WIDGET_ORIGIN) =>
  window.dispatchEvent(new MessageEvent('message', {origin, data: {type: 'i2g-embed-resize', slug: SLUG, ...data}}));

describe('CMS embed widget snippet (admin static)', () => {
  const listeners: EventListenerOrEventListenerObject[] = [];

  beforeEach(() => {
    const add = window.addEventListener.bind(window);
    vi.spyOn(window, 'addEventListener').mockImplementation((type, listener, options) => {
      if (type === 'message' && listener) listeners.push(listener);
      add(type, listener, options);
    });
  });

  afterEach(() => {
    listeners.splice(0).forEach((listener) => window.removeEventListener('message', listener));
    vi.restoreAllMocks();
    Reflect.deleteProperty(window, 'ITGEmbedSnippet');
    document.body.replaceChildren();
  });

  it('lets the widget write to the clipboard and sizes the iframe from its resize messages', () => {
    const iframe = pasteSnippet();
    expect(iframe.getAttribute('src')).toBe(`${WIDGET_ORIGIN}/_embed/${SLUG}`);
    expect(iframe.getAttribute('allow')).toBe('clipboard-write');

    postResize({height: 1146});
    expect(iframe.style.height).toBe('1146px');

    postResize({height: 345});
    expect(iframe.style.height).toBe('345px');
  });

  it('ignores resize messages from other origins and for other widgets', () => {
    const iframe = pasteSnippet();
    postResize({height: 900});

    postResize({height: 20}, 'https://ads.example.com');
    postResize({height: 20, slug: 'other-widget'});
    expect(iframe.style.height).toBe('900px');
  });

  it('keeps the iframe height while the widget has rendered nothing yet', () => {
    const iframe = pasteSnippet();
    postResize({height: 900});

    postResize({height: 0});
    postResize({height: 'tall'});
    expect(iframe.style.height).toBe('900px');
  });
});
