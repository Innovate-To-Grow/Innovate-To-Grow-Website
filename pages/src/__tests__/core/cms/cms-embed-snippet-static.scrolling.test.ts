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
const repoRoot = resolve(testDir, '../../../../..');
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

/** A message from the given frame, as the widget's scroll protocol posts it to the partner page. */
const postFrom = (frame: HTMLIFrameElement, data: Record<string, unknown>, origin = WIDGET_ORIGIN) =>
  window.dispatchEvent(new MessageEvent('message', {origin, source: frame.contentWindow, data: {slug: SLUG, ...data}}));

const postHello = (frame: HTMLIFrameElement, origin = WIDGET_ORIGIN) =>
  postFrom(frame, {type: 'i2g-embed-scroll-hello'}, origin);

/** Another iframe on the partner page, e.g. a second widget or an ad, with its own window. */
function addFrame(slug?: string): HTMLIFrameElement {
  const frame = document.createElement('iframe');
  if (slug !== undefined) frame.dataset.i2gEmbed = slug;
  document.body.append(frame);
  return frame;
}

const spyOnReady = (frame: HTMLIFrameElement) =>
  vi.spyOn(frame.contentWindow!, 'postMessage').mockImplementation(() => {});

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

  describe('scrolling the page for the widget', () => {
    it('answers the hello of its own frame, to that frame and the widget origin only', () => {
      const iframe = pasteSnippet();
      const twin = addFrame(SLUG);
      const ready = spyOnReady(iframe);
      const twinReady = spyOnReady(twin);

      postHello(iframe);

      expect(ready).toHaveBeenCalledOnce();
      expect(ready).toHaveBeenCalledWith({type: 'i2g-embed-scroll-ready'}, WIDGET_ORIGIN);
      expect(twinReady).not.toHaveBeenCalled();
      expect(iframe.style.height).toBe('');
    });

    it('ignores a hello from another origin, another widget or a frame that is not its own', () => {
      const iframe = pasteSnippet();
      const ready = spyOnReady(iframe);
      const otherWidget = addFrame('other-widget');
      const otherWidgetReady = spyOnReady(otherWidget);
      const stranger = addFrame();
      const strangerReady = spyOnReady(stranger);

      postHello(iframe, 'https://ads.example.com');
      postFrom(iframe, {type: 'i2g-embed-scroll-hello', slug: 'other-widget'});
      postHello(otherWidget);
      postFrom(otherWidget, {type: 'i2g-embed-scroll-hello', slug: 'other-widget'});
      postHello(stranger);
      window.dispatchEvent(
        new MessageEvent('message', {origin: WIDGET_ORIGIN, data: {type: 'i2g-embed-scroll-hello', slug: SLUG}}),
      );
      expect(ready).not.toHaveBeenCalled();
      expect(otherWidgetReady).not.toHaveBeenCalled();
      expect(strangerReady).not.toHaveBeenCalled();

      postHello(iframe);
      expect(ready).toHaveBeenCalledOnce();
    });
  });
});
