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
