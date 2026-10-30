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

/** A message from the given frame, as the widget's scroll protocol posts it to the partner page. */
const postFrom = (frame: HTMLIFrameElement, data: Record<string, unknown>, origin = WIDGET_ORIGIN) =>
  window.dispatchEvent(new MessageEvent('message', {origin, source: frame.contentWindow, data: {slug: SLUG, ...data}}));

const postHello = (frame: HTMLIFrameElement, origin = WIDGET_ORIGIN) =>
  postFrom(frame, {type: 'i2g-embed-scroll-hello'}, origin);

const postIntoView = (frame: HTMLIFrameElement, data: Record<string, unknown>, origin = WIDGET_ORIGIN) =>
  postFrom(frame, {type: 'i2g-embed-scroll-into-view', smooth: false, ...data}, origin);

/** Another iframe on the partner page, e.g. a second widget or an ad, with its own window. */
function addFrame(slug?: string): HTMLIFrameElement {
  const frame = document.createElement('iframe');
  if (slug !== undefined) frame.dataset.i2gEmbed = slug;
  document.body.append(frame);
  return frame;
}

const spyOnReady = (frame: HTMLIFrameElement) =>
  vi.spyOn(frame.contentWindow!, 'postMessage').mockImplementation(() => {});

/**
 * Lays out the partner page: the viewport is `viewportHeight` tall and scrolled `scrollY` down, and the frame's
 * top is `frameTop` from the top of the viewport. Returns the spy on window.scrollTo.
 */
function layOut(frame: HTMLIFrameElement, {frameTop, viewportHeight = 800, scrollY = 1000}: {
  frameTop: number;
  viewportHeight?: number;
  scrollY?: number;
}) {
  vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(viewportHeight);
  vi.spyOn(window, 'pageYOffset', 'get').mockReturnValue(scrollY);
  vi.spyOn(frame, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, frameTop, 1024, 3000));
  return vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
}

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

    it("scrolls the box's top to the top of the screen for block 'start'", () => {
      const iframe = pasteSnippet();
      const scrollTo = layOut(iframe, {frameTop: 300});

      // Box at 300 + 500 = 800 on screen: the page scrolls 800 further down.
      postIntoView(iframe, {top: 500, height: 200, block: 'start'});
      expect(scrollTo).toHaveBeenLastCalledWith({top: 1800, behavior: 'auto'});

      // Box at 300 - 500 = -200, above the screen, smoothly: the page scrolls back up.
      postIntoView(iframe, {top: -500, height: 200, block: 'start', smooth: true});
      expect(scrollTo).toHaveBeenLastCalledWith({top: 800, behavior: 'smooth'});
      expect(scrollTo).toHaveBeenCalledTimes(2);
    });

    it("scrolls only as far as needed for block 'nearest'", () => {
      const iframe = pasteSnippet();
      const scrollTo = layOut(iframe, {frameTop: 300, viewportHeight: 800});

      // [700, 900) runs 100 past the bottom: its bottom comes up to the bottom of the screen.
      postIntoView(iframe, {top: 400, height: 200, block: 'nearest'});
      expect(scrollTo).toHaveBeenLastCalledWith({top: 1100, behavior: 'auto'});

      // [-100, 100) starts 100 above the top: its top comes down to the top of the screen.
      postIntoView(iframe, {top: -400, height: 200, block: 'nearest', smooth: true});
      expect(scrollTo).toHaveBeenLastCalledWith({top: 900, behavior: 'smooth'});

      // [500, 1500) is taller than the screen and runs past the bottom: its top goes to the top.
      postIntoView(iframe, {top: 200, height: 1000, block: 'nearest'});
      expect(scrollTo).toHaveBeenLastCalledWith({top: 1500, behavior: 'auto'});

      // [-900, 100) is taller than the screen and starts above it: its bottom goes to the bottom.
      postIntoView(iframe, {top: -1200, height: 1000, block: 'nearest'});
      expect(scrollTo).toHaveBeenLastCalledWith({top: 300, behavior: 'auto'});
      expect(scrollTo).toHaveBeenCalledTimes(4);
    });

    it("leaves the page alone for block 'nearest' when the box is already on screen, or covers it", () => {
      const iframe = pasteSnippet();
      const scrollTo = layOut(iframe, {frameTop: 300, viewportHeight: 800});

      postIntoView(iframe, {top: -300, height: 800, block: 'nearest'}); // [0, 800): exactly on screen
      postIntoView(iframe, {top: 100, height: 200, block: 'nearest'}); // [400, 600)
      postIntoView(iframe, {top: -500, height: 1200, block: 'nearest'}); // [-200, 1000): covers the screen
      expect(scrollTo).not.toHaveBeenCalled();

      postIntoView(iframe, {top: 400, height: 200, block: 'nearest'});
      expect(scrollTo).toHaveBeenCalledOnce();
    });

    it('measures the frame that asked when the widget is on the page twice', () => {
      pasteSnippet();
      const twin = addFrame(SLUG);
      const scrollTo = layOut(twin, {frameTop: -2000});

      postIntoView(twin, {top: 2500, height: 100, block: 'start'});
      expect(scrollTo).toHaveBeenCalledWith({top: 1500, behavior: 'auto'});
    });

    it('ignores into-view messages without finite numbers, with an unknown block, or from a foreign frame', () => {
      const iframe = pasteSnippet();
      const stranger = addFrame();
      const scrollTo = layOut(iframe, {frameTop: 300});

      postIntoView(iframe, {top: Number.NaN, height: 200, block: 'start'});
      postIntoView(iframe, {top: Number.POSITIVE_INFINITY, height: 200, block: 'start'});
      postIntoView(iframe, {top: '500', height: 200, block: 'start'});
      postIntoView(iframe, {top: 500, height: Number.NaN, block: 'nearest'});
      postIntoView(iframe, {top: 500, height: Number.NEGATIVE_INFINITY, block: 'nearest'});
      postIntoView(iframe, {top: 500, height: null, block: 'nearest'});
      postIntoView(iframe, {top: 500, block: 'start'});
      postIntoView(iframe, {top: 500, height: 200, block: 'end'});
      postIntoView(iframe, {top: 500, height: 200, block: 'start'}, 'https://ads.example.com');
      postIntoView(stranger, {top: 500, height: 200, block: 'start'});
      expect(scrollTo).not.toHaveBeenCalled();

      postIntoView(iframe, {top: 500, height: 200, block: 'start'});
      expect(scrollTo).toHaveBeenCalledOnce();
    });

    it('still sizes the iframe from resize messages, which never scroll the page', () => {
      const iframe = pasteSnippet();
      const scrollTo = layOut(iframe, {frameTop: 300});

      postResize({height: 1146});
      expect(iframe.style.height).toBe('1146px');
      expect(scrollTo).not.toHaveBeenCalled();

      postIntoView(iframe, {top: 500, height: 200, block: 'start'});
      expect(scrollTo).toHaveBeenCalledOnce();
      expect(iframe.style.height).toBe('1146px');
    });
  });
});
