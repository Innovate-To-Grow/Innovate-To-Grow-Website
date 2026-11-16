import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  useHeaderMetrics,
} from '@/features/layout/components/MainMenu/header/useHeaderScroll';

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

afterEach(() => {
  cleanup();
  setScrollY(0);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  for (const property of HEIGHT_PROPERTIES) document.documentElement.style.removeProperty(property);
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
