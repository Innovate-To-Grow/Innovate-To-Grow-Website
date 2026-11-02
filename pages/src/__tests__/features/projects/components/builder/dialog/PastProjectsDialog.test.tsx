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

  it('boxes a destructive confirm in red, like the control that opened it, and leaves Cancel outlined navy', () => {
    const {unmount} = render(<DialogHarness destructive />);
    openFromButton();
    let dialog = screen.getByRole('dialog');
    const confirm = dialog.querySelector('.past-projects-dialog-actions > :last-child');
    expect(confirm).toHaveClass('itg-btn', 'itg-btn-outline', 'itg-btn-danger');
    expect(confirm).not.toHaveClass('itg-btn-primary');
    expect(screen.getByRole('button', {name: 'Cancel'})).toHaveClass('itg-btn-outline');
    expect(screen.getByRole('button', {name: 'Cancel'})).not.toHaveClass('itg-btn-danger');
    unmount();

    render(<DialogHarness />);
    openFromButton();
    dialog = screen.getByRole('dialog');
    expect(dialog.querySelector('.past-projects-dialog-actions > :last-child')).toHaveClass('itg-btn', 'itg-btn-primary');
    expect(dialog.querySelector('.itg-btn-danger')).toBeNull();
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
    fireEvent.click(screen.getByRole('dialog').querySelector('.itg-btn-danger')!);
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
      expect(showModal).toHaveBeenCalledTimes(1);
      expect(dialog.querySelector('.itg-btn-primary')).toHaveFocus();
    });

    it('keeps its full height when only a thin strip of the frame is on screen, and brings all of it on screen', () => {
      // The visitor scrolled the partner page until only the frame's bottom 130px show; the dialog is 196px tall.
      vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockImplementation(function (this: HTMLElement) {
        return this.tagName === 'DIALOG' ? 196 : 0;
      });
      const scrolled: Array<{top: string; height: string; block: ScrollLogicalPosition | undefined}> = [];
      Element.prototype.scrollIntoView = function (this: HTMLElement, options?: boolean | ScrollIntoViewOptions) {
        scrolled.push({top: this.style.top, height: this.style.height, block: (options as ScrollIntoViewOptions).block});
      };
      render(<DialogHarness />);
      openFromButton();

      act(() => observe({top: 7795, height: 130, bottom: 7925}));

      const dialog = screen.getByRole('dialog');
      // Not squeezed into the strip: no height limit, and it ends 16px above the frame's bottom.
      expect(dialog.style.getPropertyValue('--past-projects-dialog-max-height')).toBe('');
      expect(dialog.style.getPropertyValue('--past-projects-dialog-center')).toBe(`${7925 - 16 - 98}px`);
      expect(dialog.querySelector('.itg-btn-primary')).toHaveFocus();
      // The partner page is scrolled just far enough to show the dialog and its margins.
      expect(scrolled).toEqual([{top: `${7925 - 16 - 196 - 16}px`, height: '228px', block: 'nearest'}]);
      delete (Element.prototype as Partial<Element>).scrollIntoView;
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
