import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  CONDENSE_HYSTERESIS_PX,
  nextCondensed,
  useHeaderCondensed,
  useHeaderMetrics,
} from '@/features/layout/components/MainMenu/useHeaderScroll';

const setScrollY = (value: number) => {
  Object.defineProperty(window, 'scrollY', {configurable: true, value});
};

const HEIGHT_PROPERTIES = ['--itg-header-bar-height', '--itg-header-menu-height'];

const publishedHeights = () => HEIGHT_PROPERTIES.map((property) => document.documentElement.style.getPropertyValue(property));

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

/** The phone header breakpoint matches (`true`) or not. */
const stubPhoneLayout = (matches: boolean) =>
  vi.stubGlobal('matchMedia', (query: string) => ({matches, media: query}) as MediaQueryList);

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

describe('nextCondensed', () => {
  it('condenses once the bar has scrolled away, and lets go just before the row unpins', () => {
    expect(nextCondensed(false, 84, 85)).toBe(false);
    expect(nextCondensed(false, 85, 85)).toBe(true);
    expect(nextCondensed(true, 85 - CONDENSE_HYSTERESIS_PX, 85)).toBe(true);
    expect(nextCondensed(true, 85 - CONDENSE_HYSTERESIS_PX - 1, 85)).toBe(false);
    // Inside the hysteresis band the state depends on where it came from.
    expect(nextCondensed(false, 81, 85)).toBe(false);
    expect(nextCondensed(true, 81, 85)).toBe(true);
  });

  it('never condenses without a measured height', () => {
    expect(nextCondensed(false, 500, 0)).toBe(false);
    expect(nextCondensed(true, 500, Number.NaN)).toBe(false);
    expect(nextCondensed(true, 500, -5)).toBe(false);
  });
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

  it('never condenses the phone header, whose one bar stays the same', () => {
    runFramesImmediately();
    stubPhoneLayout(true);
    setScrollY(600);
    const {ref} = makeMeasuredHeader();
    const {result} = renderHook(() => useHeaderCondensed(ref));
    expect(result.current.isCondensed).toBe(false);
    scrollTo(900);
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
    stubPhoneLayout(false);
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

describe('useHeaderMetrics', () => {
  it('publishes the measured heights before paint and watches each header part', () => {
    installResizeObserverStub();
    const {ref, bar, menu} = makeMeasuredHeader();
    renderHook(() => useHeaderMetrics(ref));

    expect(publishedHeights()).toEqual(['85px', '40px']);
    expect(ResizeObserverStub.instances).toHaveLength(1);
    expect(ResizeObserverStub.instances[0].observed).toEqual([bar, menu]);
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
    expect(publishedHeights()).toEqual(['85px', '40px']);
    expect(frames).toHaveLength(1);

    act(() => frames[0](0));
    expect(publishedHeights()).toEqual(['96px', '40px']);

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
    expect(publishedHeights()).toEqual(['85px', '40px']);

    setHeight(menu, 48);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(publishedHeights()).toEqual(['85px', '48px']);

    unmount();
    setHeight(menu, 60);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(publishedHeights()).toEqual(['85px', '48px']);
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
    expect(publishedHeights()).toEqual(['', '']);
    expect(ResizeObserverStub.instances).toHaveLength(0);
  });
});
