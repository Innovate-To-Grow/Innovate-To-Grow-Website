import {act, renderHook} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {askPartnerPageToScroll, scrollPartnerPageBy} from '@/features/projects/components/shared/utils/partnerFrame';
import {
  MERGED_RESULTS_ID,
  scrollToMergedResults,
  useKeepScrollAnchor,
} from '@/features/projects/components/builder/selection/scrollAnchor';

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

describe('a partner page whose snippet scrolls the page for the widget (WebKit cannot scrollIntoView across sites)', () => {
  let partnerPage: {postMessage: ReturnType<typeof vi.fn>};
  let stopAsking: () => void;

  const answer = (data: unknown, source: unknown = partnerPage) => {
    const event = new MessageEvent('message', {data});
    Object.defineProperty(event, 'source', {value: source});
    window.dispatchEvent(event);
  };
  const scrollRequests = () =>
    partnerPage.postMessage.mock.calls
      .map(([message]) => message as {type: string})
      .filter((message) => message.type === 'i2g-embed-scroll-into-view');

  beforeEach(() => {
    window.history.replaceState(null, '', '/_embed/past%20widget');
    partnerPage = {postMessage: vi.fn()};
    vi.spyOn(window, 'parent', 'get').mockReturnValue(partnerPage as unknown as Window);
    stopAsking = askPartnerPageToScroll();
  });

  afterEach(() => {
    stopAsking();
    window.history.replaceState(null, '', '/');
  });

  it('asks the partner page, with the slug its resize messages carry, whether it scrolls when asked', () => {
    expect(partnerPage.postMessage).toHaveBeenCalledWith({type: 'i2g-embed-scroll-hello', slug: 'past widget'}, '*');
  });

  it('asks the partner page to scroll by the distance once it said it can, instead of scrolling into view', () => {
    answer({type: 'i2g-embed-scroll-ready'});
    scrollPartnerPageBy(628);
    window.dispatchEvent(new Event('resize'));
    observe?.({top: 3000, height: 900});

    expect(scrolled).toEqual([]);
    expect(scrollRequests()).toEqual([
      {type: 'i2g-embed-scroll-into-view', slug: 'past widget', top: 3628, height: 900, block: 'start', smooth: false},
    ]);
  });

  it('keeps scrolling into view while the partner page has not answered, or someone else did', () => {
    answer({type: 'i2g-embed-scroll-ready'}, window);
    scrollPartnerPageBy(628);
    window.dispatchEvent(new Event('resize'));
    observe?.({top: 3000, height: 900});

    expect(scrollRequests()).toEqual([]);
    expect(scrolled).toEqual([{top: '3628px', height: '900px', block: 'start'}]);
  });

  it('forgets the answer when the builder stops listening', () => {
    answer({type: 'i2g-embed-scroll-ready'});
    stopAsking();
    scrollPartnerPageBy(628);
    window.dispatchEvent(new Event('resize'));
    observe?.({top: 3000, height: 900});

    expect(scrollRequests()).toEqual([]);
    expect(scrolled).toHaveLength(1);
  });

  it('asks it to bring the curation draft to the top of the screen for View Curation Draft', () => {
    vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(4000);
    vi.spyOn(document.documentElement, 'scrollHeight', 'get').mockReturnValue(4000);
    vi.stubGlobal('matchMedia', (query: string) => ({matches: query.includes('reduce')}));
    const section = document.createElement('section');
    section.id = MERGED_RESULTS_ID;
    document.body.append(section);
    vi.spyOn(section, 'getBoundingClientRect').mockReturnValue({top: 150, height: 700} as DOMRect);
    answer({type: 'i2g-embed-scroll-ready'});

    scrollToMergedResults();

    expect(scrollRequests()).toEqual([
      {type: 'i2g-embed-scroll-into-view', slug: 'past widget', top: 150, height: 700, block: 'start', smooth: false},
    ]);
    expect(scrolled).toEqual([]);
    section.remove();
  });

  it('says nothing outside the widget', () => {
    stopAsking();
    partnerPage.postMessage.mockClear();
    window.history.replaceState(null, '', '/past-projects');
    stopAsking = askPartnerPageToScroll();

    expect(partnerPage.postMessage).not.toHaveBeenCalled();
  });
});
