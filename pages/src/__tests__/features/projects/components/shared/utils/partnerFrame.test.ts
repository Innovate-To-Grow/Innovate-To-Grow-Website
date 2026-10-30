import {act, renderHook} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {scrollPartnerPageBy} from '@/features/projects/components/shared/utils/partnerFrame';
import {useKeepScrollAnchor} from '@/features/projects/components/builder/selection/scrollAnchor';

// In the partner widget the frame is as tall as its content and the partner page scrolls, so keeping something in
// place on screen means scrolling the partner page, which only scrollIntoView can do from inside the frame.

let observe: ((rect: Partial<DOMRectReadOnly>) => void) | null;
let scrolled: Array<{top: string; height: string; block: ScrollLogicalPosition | undefined}>;

beforeEach(() => {
  vi.useFakeTimers();
  // A tall widget: the frame is as tall as its content.
  vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(7925);
  observe = null;
  scrolled = [];
  class FakeIntersectionObserver {
    constructor(callback: IntersectionObserverCallback) {
      observe = (rect) =>
        callback([{intersectionRect: rect} as IntersectionObserverEntry], this as unknown as IntersectionObserver);
    }
    observe() {}
    disconnect() {}
  }
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
  Element.prototype.scrollIntoView = function (this: HTMLElement, options?: boolean | ScrollIntoViewOptions) {
    scrolled.push({
      top: this.style.top,
      height: this.style.height,
      block: typeof options === 'object' ? options.block : undefined,
    });
  };
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete (Element.prototype as Partial<Element>).scrollIntoView;
});

describe('scrollPartnerPageBy', () => {
  it('waits for the partner page to resize the frame, then lines a box moved by the distance up with the top', () => {
    scrollPartnerPageBy(628);
    expect(observe).toBeNull();

    window.dispatchEvent(new Event('resize'));
    // The frame runs past the top of the screen: 3000px of it are above.
    observe?.({top: 3000, height: 900});

    expect(scrolled).toEqual([{top: '3628px', height: '900px', block: 'start'}]);
    expect(document.body.children).toHaveLength(0);
  });

  it('waits while the partner page resizes the frame in steps, until the frame fits its content', () => {
    let scrollHeight = 1973;
    vi.spyOn(document.documentElement, 'scrollHeight', 'get').mockImplementation(() => scrollHeight);
    vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(1838);
    scrollPartnerPageBy(628);

    // Still 135px short: the frame's own document would take that part of the scroll.
    window.dispatchEvent(new Event('resize'));
    expect(observe).toBeNull();

    scrollHeight = 1838;
    window.dispatchEvent(new Event('resize'));
    observe?.({top: 469, height: 900});
    expect(scrolled).toEqual([{top: '1097px', height: '741px', block: 'start'}]);
  });

  it('keeps the box within the frame, so the frame itself never gets room to scroll', () => {
    vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(1838);
    scrollPartnerPageBy(628);
    window.dispatchEvent(new Event('resize'));
    // 469 + 628 + 900 would end 135px below the frame.
    observe?.({top: 469, height: 900});

    expect(scrolled).toEqual([{top: '1097px', height: '741px', block: 'start'}]);
  });

  it('scrolls just far enough when the frame starts on screen', () => {
    scrollPartnerPageBy(628);
    window.dispatchEvent(new Event('resize'));
    observe?.({top: 0, height: 600});

    expect(scrolled).toEqual([{top: '628px', height: '600px', block: 'nearest'}]);
  });

  it('goes on without the resize after a moment, once only', () => {
    scrollPartnerPageBy(-200);
    vi.advanceTimersByTime(1000);
    observe?.({top: 1200, height: 900});
    window.dispatchEvent(new Event('resize'));

    expect(scrolled).toEqual([{top: '1000px', height: '900px', block: 'start'}]);
  });

  it('does nothing when the observer cannot say what is on screen', () => {
    scrollPartnerPageBy(628);
    window.dispatchEvent(new Event('resize'));
    vi.advanceTimersByTime(300);

    expect(scrolled).toEqual([]);
  });
});

describe('useKeepScrollAnchor in the partner widget', () => {
  it('scrolls the partner page, not the frame, by how far the anchor moved', () => {
    vi.spyOn(window, 'parent', 'get').mockReturnValue({} as Window);
    vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(4000);
    vi.spyOn(document.documentElement, 'scrollHeight', 'get').mockReturnValue(4000);
    const scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
    const anchorElement = document.createElement('section');
    document.body.append(anchorElement);
    let anchorTop = 2000;
    vi.spyOn(anchorElement, 'getBoundingClientRect').mockImplementation(() => ({top: anchorTop}) as DOMRect);

    const {result, rerender} = renderHook(({dependency}) => useKeepScrollAnchor(dependency), {
      initialProps: {dependency: 0},
    });
    act(() => {
      result.current.current = {element: anchorElement, top: 2000, inAutoHeightFrame: true};
    });
    anchorTop = 2628;
    rerender({dependency: 1});
    window.dispatchEvent(new Event('resize'));
    observe?.({top: 1800, height: 900});

    expect(scrollBy).not.toHaveBeenCalled();
    expect(scrolled).toEqual([{top: '2428px', height: '900px', block: 'start'}]);
    anchorElement.remove();
  });
});
