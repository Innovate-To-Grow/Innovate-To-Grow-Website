import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {useStatusLineInView} from '@/features/projects/components/merged/list/useStatusLineInView';

/** A draft card: a row's Remove, and the status line under the table. */
const Card = ({message, reports}: {message: string; reports: number}) => {
  const {cardRef, lineRef, onPointerDown} = useStatusLineInView(message, reports);
  return (
    <section ref={cardRef} onPointerDown={onPointerDown}>
      <button type="button">Remove Bravo Project</button>
      <p ref={lineRef} role="status">
        {message}
      </p>
    </section>
  );
};

const placeAt = (element: Element, top: number, bottom = top + 24) =>
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({top, bottom} as DOMRect);

describe('useStatusLineInView', () => {
  let scrollBy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(900);
    scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  /** Renders the card with its line at `lineTop` (the 4-row draft at 1280x900: 958) and a Remove at `removeTop`. */
  const renderCard = (lineTop: number, removeTop: number) => {
    const {rerender} = render(<Card message="" reports={0} />);
    let reports = 0;
    placeAt(screen.getByRole('status'), lineTop);
    const remove = screen.getByRole('button', {name: 'Remove Bravo Project'});
    placeAt(remove, removeTop);
    return {remove, report: (message: string) => rerender(<Card message={message} reports={(reports += 1)} />)};
  };

  it('scrolls a message about a row the visitor removed into view, just far enough', () => {
    const {remove, report} = renderCard(958, 420);
    remove.focus();

    report('Project removed from the curation draft.');

    // 958 + 24 + 16 - 900: the line and a 16px margin.
    expect(scrollBy).toHaveBeenCalledExactlyOnceWith(0, 98);
  });

  it('scrolls a message that repeats the line again, once the visitor scrolled it away', () => {
    const {remove, report} = renderCard(958, 420);
    remove.focus();
    report('Project removed from the curation draft.');
    report('Project removed from the curation draft.');

    expect(scrollBy).toHaveBeenCalledTimes(2);
  });

  it('also follows a press that did not focus the button (Safari)', () => {
    const {remove, report} = renderCard(958, 420);
    fireEvent.pointerDown(remove, {clientY: 430});

    report('Project removed from the curation draft.');

    expect(scrollBy).toHaveBeenCalledExactlyOnceWith(0, 98);
  });

  it('does not move what the visitor acted on off the top of the screen', () => {
    const {remove, report} = renderCard(958, 90);
    remove.focus();

    report('Project removed from the curation draft.');

    expect(scrollBy).not.toHaveBeenCalled();
  });

  it('leaves the page alone for a message the card did not cause, or a line already on screen', () => {
    const {remove, report} = renderCard(958, 420);
    report('The curation draft was changed in another tab.');
    expect(scrollBy).not.toHaveBeenCalled();

    placeAt(screen.getByRole('status'), 700);
    remove.focus();
    report('Project removed from the curation draft.');
    expect(scrollBy).not.toHaveBeenCalled();
  });
});

describe('useStatusLineInView in the partner widget', () => {
  // The frame is as tall as its content and the partner page scrolls: the line is placed against the part of the
  // frame on the visitor's screen, and the partner page is scrolled (through scrollIntoView or its snippet).
  let observe: ((rect: Partial<DOMRectReadOnly>) => void) | null;
  let scrolled: Array<{top: string; height: string; block: ScrollLogicalPosition | undefined}>;
  let scrollBy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.spyOn(window, 'parent', 'get').mockReturnValue({} as Window);
    vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(4000);
    vi.spyOn(document.documentElement, 'scrollHeight', 'get').mockReturnValue(4000);
    scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
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
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete (Element.prototype as Partial<Element>).scrollIntoView;
  });

  const renderRemoved = (lineTop: number, removeTop: number) => {
    const {rerender} = render(<Card message="" reports={0} />);
    placeAt(screen.getByRole('status'), lineTop);
    const remove = screen.getByRole('button', {name: 'Remove Bravo Project'});
    placeAt(remove, removeTop);
    remove.focus();
    rerender(<Card message="Project removed from the curation draft." reports={1} />);
  };

  it('scrolls the partner page just far enough to show a line below the visitor\'s screen', () => {
    // 1500px of the frame are above the screen; the line, 1018px down the frame's screenful, is below it.
    renderRemoved(2518, 1920);
    observe?.({top: 1500, bottom: 2400, height: 900});

    // The line and a 16px margin, brought up to the screen's bottom edge: the partner page scrolls 158px.
    expect(scrolled).toEqual([{top: '2518px', height: '40px', block: 'nearest'}]);
    expect(scrollBy).not.toHaveBeenCalled();
  });

  it('leaves the partner page alone when what was acted on would leave the screen, or the line is on it', () => {
    renderRemoved(2518, 1600);
    observe?.({top: 1500, bottom: 2400, height: 900});
    expect(scrolled).toEqual([]);

    cleanup();
    renderRemoved(2300, 1920);
    observe?.({top: 1500, bottom: 2400, height: 900});
    expect(scrolled).toEqual([]);
    expect(scrollBy).not.toHaveBeenCalled();
  });
});
