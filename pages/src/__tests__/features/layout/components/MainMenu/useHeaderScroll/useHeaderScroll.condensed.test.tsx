import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  useHeaderCondensed,
} from '@/features/layout/components/MainMenu/useHeaderScroll';

const setScrollY = (value: number) => {
  Object.defineProperty(window, 'scrollY', {configurable: true, value});
};

const HEIGHT_PROPERTIES = ['--itg-header-bar-height', '--itg-header-menu-height'];

const setHeight = (element: HTMLElement, height: number) => {
  element.getBoundingClientRect = () =>
    ({height, width: 0, top: 0, left: 0, right: 0, bottom: height, x: 0, y: 0, toJSON: () => ({})}) as DOMRect;
};

/** A header with its bar and menu row, each a known height. */
const makeMeasuredHeader = () => {
  const header = document.createElement('header');
  const parts = Object.fromEntries(
    (
      [
        ['bar', 'site-header-bar', 85],
        ['menu', 'site-header-menu', 40],
      ] as const
    ).map(([key, className, height]) => {
      const element = document.createElement('div');
      element.className = className;
      setHeight(element, height);
      header.appendChild(element);
      return [key, element];
    }),
  ) as Record<'bar' | 'menu', HTMLDivElement>;
  return {ref: {current: header}, ...parts};
};

/** Runs each requested animation frame straight away. */
const runFramesImmediately = () =>
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    callback(0);
    return 1;
  });

/** Collects requested animation frames so a test can run them one at a time. */
const collectFrames = () => {
  const frames: FrameRequestCallback[] = [];
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    frames.push(callback);
    return frames.length;
  });
  return frames;
};

const scrollTo = (value: number) =>
  act(() => {
    setScrollY(value);
    window.dispatchEvent(new Event('scroll'));
  });

afterEach(() => {
  cleanup();
  setScrollY(0);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  for (const property of HEIGHT_PROPERTIES) document.documentElement.style.removeProperty(property);
});

describe('useHeaderCondensed', () => {
  it('starts condensed when the page loads already scrolled past the bar', () => {
    setScrollY(300);
    const {ref} = makeMeasuredHeader();
    const {result} = renderHook(() => useHeaderCondensed(ref));
    expect(result.current.isCondensed).toBe(true);
  });

  it('condenses when the menu row pins and goes back near the top', () => {
    runFramesImmediately();
    const {ref} = makeMeasuredHeader();
    // The 85px bar is above the row: it pins at 85px.
    const {result} = renderHook(() => useHeaderCondensed(ref));
    expect(result.current.isCondensed).toBe(false);

    scrollTo(60);
    expect(result.current.isCondensed).toBe(false);
    scrollTo(85);
    expect(result.current.isCondensed).toBe(true);
    scrollTo(81);
    expect(result.current.isCondensed).toBe(true);
    scrollTo(76);
    expect(result.current.isCondensed).toBe(false);
  });

  it('condenses the phone header too, once the page has scrolled by its 61px bar', () => {
    runFramesImmediately();
    const {ref, bar} = makeMeasuredHeader();
    setHeight(bar, 61);
    const {result} = renderHook(() => useHeaderCondensed(ref));
    scrollTo(60);
    expect(result.current.isCondensed).toBe(false);
    scrollTo(61);
    expect(result.current.isCondensed).toBe(true);
    scrollTo(53);
    expect(result.current.isCondensed).toBe(true);
    scrollTo(52);
    expect(result.current.isCondensed).toBe(false);
  });

  it('never condenses without a bar above the row, or without a mounted header', () => {
    runFramesImmediately();
    const {ref, bar} = makeMeasuredHeader();
    bar.remove();
    const {result} = renderHook(() => useHeaderCondensed(ref));
    scrollTo(900);
    expect(result.current.isCondensed).toBe(false);

    const {result: unmounted} = renderHook(() => useHeaderCondensed({current: null}));
    scrollTo(900);
    expect(unmounted.current.isCondensed).toBe(false);
  });

  it('re-checks on resize, when the bar height changes', () => {
    runFramesImmediately();
    setScrollY(100);
    const {ref, bar} = makeMeasuredHeader();
    const {result} = renderHook(() => useHeaderCondensed(ref));
    expect(result.current.isCondensed).toBe(true);

    // The bar grows past the scroll offset: the row is no longer pinned.
    setHeight(bar, 117);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(result.current.isCondensed).toBe(false);
  });

  it('coalesces scroll events into one update per animation frame', () => {
    const frames = collectFrames();
    const {ref} = makeMeasuredHeader();
    const {result} = renderHook(() => useHeaderCondensed(ref));
    const pending = frames.length;

    act(() => {
      setScrollY(400);
      window.dispatchEvent(new Event('scroll'));
      window.dispatchEvent(new Event('scroll'));
      window.dispatchEvent(new Event('resize'));
    });
    expect(frames).toHaveLength(pending + 1);
    expect(result.current.isCondensed).toBe(false);

    act(() => frames[pending](0));
    expect(result.current.isCondensed).toBe(true);
  });

  it('turns motion on only after the first state has been painted', () => {
    const frames = collectFrames();
    const {ref} = makeMeasuredHeader();
    const {result} = renderHook(() => useHeaderCondensed(ref));
    expect(result.current.hasMotion).toBe(false);

    act(() => frames[0](0));
    expect(result.current.hasMotion).toBe(false);
    act(() => frames[1](0));
    expect(result.current.hasMotion).toBe(true);
  });

  it('stops listening on unmount', () => {
    const cancel = vi.spyOn(window, 'cancelAnimationFrame');
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(7);
    const {ref} = makeMeasuredHeader();
    const {unmount} = renderHook(() => useHeaderCondensed(ref));
    window.dispatchEvent(new Event('scroll'));
    unmount();
    expect(cancel).toHaveBeenCalledWith(7);

    raf.mockClear();
    window.dispatchEvent(new Event('scroll'));
    window.dispatchEvent(new Event('resize'));
    expect(raf).not.toHaveBeenCalled();
  });
});
