import {useState} from 'react';
import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsDialog} from '@/features/projects/components/builder/dialog/PastProjectsDialog';

/** An opener button and the dialog it opens, as the builder uses them. */
const DialogHarness = ({destructive = false, onConfirm = () => {}}: {destructive?: boolean; onConfirm?: () => void}) => {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setIsOpen(true)}>
        Clear Draft
      </button>
      {isOpen ? (
        <PastProjectsDialog
          title="Clear the curation draft?"
          confirmLabel="Clear Draft"
          destructive={destructive}
          onCancel={() => setIsOpen(false)}
          onConfirm={() => {
            onConfirm();
            setIsOpen(false);
          }}
        >
          <p>Remove every project from the curation draft?</p>
        </PastProjectsDialog>
      ) : null}
    </>
  );
};

const openFromButton = () => {
  const opener = screen.getByRole('button', {name: 'Clear Draft'});
  opener.focus();
  fireEvent.click(opener);
  return opener;
};

describe('PastProjectsDialog', () => {
  let showModal: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // jsdom has no modal dialogs; record the call and show the dialog the way a browser would.
    showModal = vi.fn(function (this: HTMLDialogElement) {
      this.setAttribute('open', '');
    });
    HTMLDialogElement.prototype.showModal = showModal as unknown as HTMLDialogElement['showModal'];
    HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
      this.removeAttribute('open');
    };
  });

  afterEach(() => {
    cleanup();
    // @ts-expect-error -- removing the test's stand-ins again
    delete HTMLDialogElement.prototype.showModal;
    // @ts-expect-error -- see above
    delete HTMLDialogElement.prototype.close;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('opens as a native modal dialog, so the page behind it is inert', () => {
    render(<DialogHarness />);
    openFromButton();

    const dialog = screen.getByRole('dialog', {name: 'Clear the curation draft?'});
    expect(dialog.tagName).toBe('DIALOG');
    expect(showModal).toHaveBeenCalledTimes(1);
    expect(dialog).toHaveAccessibleDescription('Remove every project from the curation draft?');
  });

  it('starts a destructive confirmation on Cancel, and any other on its confirm button', () => {
    const {unmount} = render(<DialogHarness destructive />);
    openFromButton();
    expect(screen.getByRole('button', {name: 'Cancel'})).toHaveFocus();
    unmount();

    render(<DialogHarness />);
    openFromButton();
    const dialog = screen.getByRole('dialog');
    expect(dialog.querySelector('.itg-btn-primary')).toHaveFocus();
  });

  it('gives focus back to the control that opened it, however it closes', () => {
    const onConfirm = vi.fn();
    render(<DialogHarness destructive onConfirm={onConfirm} />);

    let opener = openFromButton();
    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();

    opener = openFromButton();
    fireEvent.keyDown(screen.getByRole('button', {name: 'Cancel'}), {key: 'Escape'});
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();

    opener = openFromButton();
    fireEvent.click(screen.getByRole('dialog').querySelector('.itg-btn-primary')!);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(opener).toHaveFocus();
  });

  it("cancels on the browser's own close request rather than closing behind the page's back", () => {
    render(<DialogHarness />);
    openFromButton();
    const dialog = screen.getByRole('dialog');

    const closeRequest = new Event('cancel', {cancelable: true});
    fireEvent(dialog, closeRequest);

    expect(closeRequest.defaultPrevented).toBe(true);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('cancels on a press on the backdrop, not on one inside the panel', () => {
    render(<DialogHarness />);
    openFromButton();
    const dialog = screen.getByRole('dialog');

    fireEvent.mouseDown(screen.getByText('Remove every project from the curation draft?'));
    expect(screen.getByRole('dialog')).toBe(dialog);

    fireEvent.mouseDown(dialog);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  describe('inside the embed widget, whose frame is as tall as its content', () => {
    let observe: (rect: Partial<DOMRectReadOnly>) => void;

    beforeEach(() => {
      vi.spyOn(window, 'parent', 'get').mockReturnValue({} as Window);
      vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(7925);
      class FakeIntersectionObserver {
        constructor(callback: IntersectionObserverCallback) {
          observe = (rect) =>
            callback([{intersectionRect: rect} as IntersectionObserverEntry], this as unknown as IntersectionObserver);
        }
        observe() {}
        disconnect() {}
      }
      vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
    });

    it('opens centred on the part of the frame the partner page shows, before it takes focus', () => {
      render(<DialogHarness />);
      openFromButton();

      // Not shown (or focused, which would scroll the partner page to the frame's middle) until it is placed.
      const dialog = document.querySelector('dialog')!;
      expect(showModal).not.toHaveBeenCalled();
      expect(dialog).not.toHaveAttribute('open');

      act(() => observe({top: 3000, height: 900, bottom: 3900}));

      expect(dialog).toHaveClass('is-placed');
      expect(dialog.style.getPropertyValue('--past-projects-dialog-center')).toBe('3450px');
      expect(dialog.style.getPropertyValue('--past-projects-dialog-max-height')).toBe('868px');
      expect(showModal).toHaveBeenCalledTimes(1);
      expect(dialog.querySelector('.itg-btn-primary')).toHaveFocus();
    });

    it('stays centred in the frame when the whole frame is on screen', () => {
      render(<DialogHarness />);
      openFromButton();

      act(() => observe({top: 0, height: 7925, bottom: 7925}));

      const dialog = screen.getByRole('dialog');
      expect(dialog).not.toHaveClass('is-placed');
      expect(showModal).toHaveBeenCalledTimes(1);
    });
  });
});
