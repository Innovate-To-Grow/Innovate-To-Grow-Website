import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  BAND_HIDE_AFTER_PX,
  BAND_SHOW_BELOW_PX,
  nextBandHidden,
  useHeaderBandHidden,
  useHeaderMetrics,
} from '@/features/layout/components/MainMenu/useHeaderScroll';

const setScrollY = (value: number) => {
  Object.defineProperty(window, 'scrollY', {configurable: true, value});
};

const HEIGHT_PROPERTIES = ['--itg-header-bar-height', '--itg-header-band-height', '--itg-header-menu-height'];

const publishedHeights = () => HEIGHT_PROPERTIES.map((property) => document.documentElement.style.getPropertyValue(property));

const setHeight = (element: HTMLElement, height: number) => {
  element.getBoundingClientRect = () =>
    ({height, width: 0, top: 0, left: 0, right: 0, bottom: height, x: 0, y: 0, toJSON: () => ({})}) as DOMRect;
};

/** A header with its bar, phone band and menu row, each a known height. */
const makeMeasuredHeader = () => {
  const header = document.createElement('header');
  const parts = Object.fromEntries(
    (
      [
        ['bar', 'site-header-bar', 85],
        ['band', 'site-header-band', 74],
        ['menu', 'site-header-menu', 40],
      ] as const
    ).map(([key, className, height]) => {
      const element = document.createElement('div');
      element.className = className;
      setHeight(element, height);
      header.appendChild(element);
      return [key, element];
    }),
  ) as Record<'bar' | 'band' | 'menu', HTMLDivElement>;
  return {ref: {current: header}, ...parts};
};

/** Stands in for the browser's ResizeObserver, which jsdom does not implement. */
class ResizeObserverStub {
  static instances: ResizeObserverStub[] = [];
  readonly observed: Element[] = [];
  disconnected = false;
  private readonly callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    ResizeObserverStub.instances.push(this);
  }

  observe(target: Element) {
    this.observed.push(target);
  }

  unobserve() {}

  disconnect() {
    this.disconnected = true;
  }

  /** Delivers a notification, as the browser does after layout. */
  notify() {
    this.callback([], this as unknown as ResizeObserver);
  }
}

const installResizeObserverStub = () => {
  ResizeObserverStub.instances = [];
  vi.stubGlobal('ResizeObserver', ResizeObserverStub);
};

/** A header whose phone site-name band is `height` px tall (the room #menu-root reserves for it). */
const makeHeaderRef = (height: number) => {
  const header = document.createElement('header');
  const band = document.createElement('div');
  band.className = 'site-header-band';
  band.getBoundingClientRect = () =>
    ({height, width: 0, top: 0, left: 0, right: 0, bottom: height, x: 0, y: 0, toJSON: () => ({})}) as DOMRect;
  header.appendChild(band);
  return {current: header, band};
};

/** Runs each requested animation frame straight away. */
const runFramesImmediately = () =>
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    callback(0);
    return 1;
  });

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

describe('nextBandHidden', () => {
  it('without reserved room, hides past the threshold and only shows again near the top', () => {
    expect(nextBandHidden(false, BAND_HIDE_AFTER_PX)).toBe(false);
    expect(nextBandHidden(false, BAND_HIDE_AFTER_PX + 1)).toBe(true);
    expect(nextBandHidden(true, BAND_SHOW_BELOW_PX + 10)).toBe(true);
    expect(nextBandHidden(true, BAND_SHOW_BELOW_PX)).toBe(true);
    expect(nextBandHidden(true, BAND_SHOW_BELOW_PX - 1)).toBe(false);
  });

  it('keeps the band while its reserved room is still under the bar, then hides it', () => {
    // Hiding at 41..84px would uncover the empty room the page keeps for the band.
    expect(nextBandHidden(false, BAND_HIDE_AFTER_PX + 1, 84)).toBe(false);
    expect(nextBandHidden(false, 84, 84)).toBe(false);
    expect(nextBandHidden(false, 85, 84)).toBe(true);
  });

  it('brings the band back as soon as its reserved room scrolls into view again', () => {
    expect(nextBandHidden(true, 300, 84)).toBe(true);
    expect(nextBandHidden(true, 84, 84)).toBe(true);
    expect(nextBandHidden(true, 83, 84)).toBe(false);
    // The case that used to leave an empty strip: back up to 20px, above the 4px show threshold.
    expect(nextBandHidden(true, 20, 84)).toBe(false);
  });

  it('ignores a missing or invalid reserved height', () => {
    expect(nextBandHidden(true, 20, 0)).toBe(true);
    expect(nextBandHidden(true, 20, Number.NaN)).toBe(true);
    expect(nextBandHidden(false, BAND_HIDE_AFTER_PX + 1, -5)).toBe(true);
  });
});

describe('useHeaderBandHidden', () => {
  it('starts hidden when the page loads already scrolled', () => {
    setScrollY(300);
    const {result} = renderHook(() => useHeaderBandHidden());
    expect(result.current).toBe(true);
  });

  it('shows the band on load when its reserved room is still in view', () => {
    setScrollY(60);
    const {current} = makeHeaderRef(84);
    const {result} = renderHook(() => useHeaderBandHidden({current}));
    expect(result.current).toBe(false);
  });

  it('hides on the way down only after the reserved room is gone, and reveals it on the way back up', () => {
    runFramesImmediately();
    const {current} = makeHeaderRef(84);
    const {result} = renderHook(() => useHeaderBandHidden({current}));
    expect(result.current).toBe(false);

    scrollTo(60);
    expect(result.current).toBe(false);
    scrollTo(300);
    expect(result.current).toBe(true);

    // Scrolling back up: hidden while the room is still above the viewport...
    scrollTo(120);
    expect(result.current).toBe(true);
    // ...and back the moment it would show as an empty strip under the bar.
    scrollTo(20);
    expect(result.current).toBe(false);

    scrollTo(300);
    expect(result.current).toBe(true);
    scrollTo(0);
    expect(result.current).toBe(false);
  });

  it('re-checks on resize, when the band height can change', () => {
    runFramesImmediately();
    setScrollY(100);
    const {current, band} = makeHeaderRef(84);
    const {result} = renderHook(() => useHeaderBandHidden({current}));
    expect(result.current).toBe(true);

    // Wider layout: the band is taller than the scroll offset, so its room is in view again.
    band.getBoundingClientRect = () =>
      ({height: 110, width: 0, top: 0, left: 0, right: 0, bottom: 110, x: 0, y: 0, toJSON: () => ({})}) as DOMRect;
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(result.current).toBe(false);
  });

  it('coalesces scroll events into one update per animation frame', () => {
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    const {result} = renderHook(() => useHeaderBandHidden());

    act(() => {
      setScrollY(200);
      window.dispatchEvent(new Event('scroll'));
      window.dispatchEvent(new Event('scroll'));
      window.dispatchEvent(new Event('resize'));
    });
    expect(frames).toHaveLength(1);
    expect(result.current).toBe(false);

    act(() => frames[0](0));
    expect(result.current).toBe(true);
  });

  it('stops listening on unmount', () => {
    const cancel = vi.spyOn(window, 'cancelAnimationFrame');
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(7);
    const {unmount} = renderHook(() => useHeaderBandHidden());
    window.dispatchEvent(new Event('scroll'));
    unmount();
    expect(cancel).toHaveBeenCalledWith(7);

    raf.mockClear();
    window.dispatchEvent(new Event('scroll'));
    window.dispatchEvent(new Event('resize'));
    expect(raf).not.toHaveBeenCalled();
  });
});

describe('useHeaderMetrics', () => {
  it('publishes the measured heights before paint and watches each header part', () => {
    installResizeObserverStub();
    const {ref, bar, band, menu} = makeMeasuredHeader();
    renderHook(() => useHeaderMetrics(ref));

    expect(publishedHeights()).toEqual(['85px', '74px', '40px']);
    expect(ResizeObserverStub.instances).toHaveLength(1);
    expect(ResizeObserverStub.instances[0].observed).toEqual([bar, band, menu]);
  });

  it('writes a reported resize on the next animation frame, once for any number of notifications', () => {
    installResizeObserverStub();
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    const {ref, bar} = makeMeasuredHeader();
    renderHook(() => useHeaderMetrics(ref));
    const [observer] = ResizeObserverStub.instances;

    // The web fonts load and the bar grows: nothing is written inside the callback.
    setHeight(bar, 96);
    observer.notify();
    observer.notify();
    expect(publishedHeights()).toEqual(['85px', '74px', '40px']);
    expect(frames).toHaveLength(1);

    act(() => frames[0](0));
    expect(publishedHeights()).toEqual(['96px', '74px', '40px']);

    // Converged: the next notification schedules a frame that rewrites nothing.
    const setProperty = vi.spyOn(document.documentElement.style, 'setProperty');
    observer.notify();
    act(() => frames[1](0));
    expect(setProperty).not.toHaveBeenCalled();
  });

  it('falls back to window resize events when ResizeObserver is missing', () => {
    vi.stubGlobal('ResizeObserver', undefined);
    const {ref, menu} = makeMeasuredHeader();
    const {unmount} = renderHook(() => useHeaderMetrics(ref));
    expect(publishedHeights()).toEqual(['85px', '74px', '40px']);

    setHeight(menu, 48);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(publishedHeights()).toEqual(['85px', '74px', '48px']);

    unmount();
    setHeight(menu, 60);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(publishedHeights()).toEqual(['85px', '74px', '48px']);
  });

  it('stops observing and drops a pending frame on unmount', () => {
    installResizeObserverStub();
    const cancel = vi.spyOn(window, 'cancelAnimationFrame');
    vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(7);
    const {ref} = makeMeasuredHeader();
    const {unmount} = renderHook(() => useHeaderMetrics(ref));
    const [observer] = ResizeObserverStub.instances;

    observer.notify();
    unmount();
    expect(observer.disconnected).toBe(true);
    expect(cancel).toHaveBeenCalledWith(7);
  });

  it('does nothing without a mounted header', () => {
    installResizeObserverStub();
    renderHook(() => useHeaderMetrics({current: null}));
    expect(publishedHeights()).toEqual(['', '', '']);
    expect(ResizeObserverStub.instances).toHaveLength(0);
  });
});
