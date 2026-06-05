import {useEffect, useId, useRef, type ReactNode} from 'react';

interface PastProjectsDialogProps {
  cancelLabel?: string;
  children: ReactNode;
  confirmLabel: string;
  title: string;
  onCancel: () => void;
  onConfirm: () => void;
}

export const PastProjectsDialog = ({
  cancelLabel = 'Cancel',
  children,
  confirmLabel,
  title,
  onCancel,
  onConfirm,
}: PastProjectsDialogProps) => {
  const titleId = useId();
  const descriptionId = useId();
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    confirmButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onCancel();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onCancel]);

  return (
    <div
      className="past-projects-dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onCancel();
        }
      }}
    >
      <section
        className="past-projects-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
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
          <button type="button" className="itg-btn itg-btn-outline" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button ref={confirmButtonRef} type="button" className="itg-btn itg-btn-primary" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
};
