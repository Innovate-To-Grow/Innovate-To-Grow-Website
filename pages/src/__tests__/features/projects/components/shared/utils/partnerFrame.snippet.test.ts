import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {askPartnerPageToScroll, scrollPartnerPageBy} from '@/features/projects/components/shared/utils/partnerFrame';
import {
  MERGED_RESULTS_ID,
  scrollToMergedResults,
} from '@/features/projects/components/curation/builder/selection/scrollAnchor';

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

describe('a partner page whose snippet scrolls the page for the widget (WebKit cannot scrollIntoView across sites)', () => {
  let partnerPage: {postMessage: ReturnType<typeof vi.fn>};
  let stopAsking: () => void;

  const answer = (data: unknown, source: unknown = partnerPage, origin = 'https://partner.example') => {
    const event = new MessageEvent('message', {data, origin});
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
    expect(partnerPage.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({type: 'i2g-embed-scroll-into-view'}),
      'https://partner.example',
    );
  });

  it('sends scroll requests to any origin when the partner page has an opaque one', () => {
    answer({type: 'i2g-embed-scroll-ready'}, partnerPage, 'null');
    scrollPartnerPageBy(628);
    window.dispatchEvent(new Event('resize'));
    observe?.({top: 3000, height: 900});

    expect(partnerPage.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({type: 'i2g-embed-scroll-into-view'}),
      '*',
    );
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
