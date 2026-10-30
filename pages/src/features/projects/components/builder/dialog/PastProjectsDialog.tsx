import {useEffect, useEffectEvent, useId, useRef, type ReactNode} from 'react';
import {openInVisiblePart} from './dialogPlacement';

interface PastProjectsDialogProps {
  cancelLabel?: string;
  children: ReactNode;
  confirmLabel: string;
  /** Confirming opens this page in a new tab: the confirm control is a link to it (and still calls onConfirm). */
  confirmHref?: string;
  /** Confirming throws work away: the dialog opens on Cancel, the safe choice. */
  destructive?: boolean;
  title: string;
  onCancel: () => void;
  onConfirm: () => void;
}

/** Shows the dialog as a modal: the rest of the page is inert and focus stays inside it. */
const showDialog = (dialog: HTMLDialogElement) => {
  if (dialog.open) {
    return;
  }
  if (typeof dialog.showModal === 'function') {
    dialog.showModal();
  } else {
    // Without showModal (jsdom), the dialog is at least shown and named.
    dialog.setAttribute('open', '');
  }
};

const closeDialog = (dialog: HTMLDialogElement) => {
  if (!dialog.open) {
    return;
  }
  if (typeof dialog.close === 'function') {
    dialog.close();
  } else {
    dialog.removeAttribute('open');
  }
};

/**
 * The builder's confirmations, as a native modal `<dialog>`: the page behind it is inert, Escape or a click
 * on the backdrop cancels, and closing it gives focus back to the control that opened it.
 */
export const PastProjectsDialog = ({
  cancelLabel = 'Cancel',
  children,
  confirmLabel,
  confirmHref,
  destructive = false,
  title,
  onCancel,
  onConfirm,
}: PastProjectsDialogProps) => {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const confirmLinkRef = useRef<HTMLAnchorElement>(null);
  const handleEscape = useEffectEvent(() => onCancel());
  const focusFirstButton = useEffectEvent(() =>
    (destructive ? cancelButtonRef.current : (confirmButtonRef.current ?? confirmLinkRef.current))?.focus(),
  );

  // Open once, on mount. Callers pass inline handlers, so an effect that depended on them re-ran on every parent
  // render and pulled focus back to the first button.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const cancelPlacement = openInVisiblePart(dialog, () => {
      showDialog(dialog);
      focusFirstButton();
    });

    // Escape is the browser's close request; cancelling the key press stops it from closing the dialog behind
    // the caller's back, which unmounts it instead.
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        handleEscape();
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      cancelPlacement();
      window.removeEventListener('keydown', handleKeyDown);
      closeDialog(dialog);
      // The dialog has left the page by now (this runs after the commit), so the page is no longer inert.
      if (opener?.isConnected) {
        opener.focus();
      }
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="past-projects-dialog"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      // A close request the key handler did not see (focus outside the dialog): cancel instead of closing.
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
      // The panel's content fills the element, so a press on the element itself is a press on the backdrop.
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onCancel();
        }
      }}
    >
      <div className="past-projects-dialog-header">
        <h2 id={titleId} className="past-projects-dialog-title">
          {title}
        </h2>
      </div>
      <div id={descriptionId} className="past-projects-dialog-body">
        {children}
      </div>
      <div className="past-projects-dialog-actions">
        <button ref={cancelButtonRef} type="button" className="itg-btn itg-btn-outline" onClick={onCancel}>
          {cancelLabel}
        </button>
        {confirmHref ? (
          <a
            ref={confirmLinkRef}
            className="itg-btn itg-btn-primary"
            href={confirmHref}
            target="_blank"
            rel="noopener"
            onClick={onConfirm}
          >
            {confirmLabel}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        ) : (
          <button ref={confirmButtonRef} type="button" className="itg-btn itg-btn-primary" onClick={onConfirm}>
            {confirmLabel}
          </button>
        )}
      </div>
    </dialog>
  );
};
