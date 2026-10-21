import {useMemo} from 'react';

function formatExpiryTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
}

interface LivePreviewNoticeProps {
  expiresAt?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** The admin live-preview notice: a dismissible modal, then a badge that reopens it. */
export const LivePreviewNotice = ({expiresAt, open: showPreviewModal, onOpenChange: setShowPreviewModal}: LivePreviewNoticeProps) => {
  const expiryDisplay = useMemo(() => (expiresAt ? formatExpiryTime(expiresAt) : null), [expiresAt]);

  if (!showPreviewModal) {
    return (
      <button type="button" className="cms-live-preview-badge" onClick={() => setShowPreviewModal(true)}>
        <span className="cms-live-preview-modal-dot" aria-hidden="true" />
        <span>CMS Preview</span>
        {expiryDisplay && <span className="cms-live-preview-badge-expiry">Expires {expiryDisplay}</span>}
      </button>
    );
  }
  return (
    <div className="cms-live-preview-overlay" onClick={() => setShowPreviewModal(false)}>
      <div className="cms-live-preview-modal" onClick={(e) => e.stopPropagation()}>
        <span className="cms-live-preview-modal-dot" aria-hidden="true" />
        <p className="cms-live-preview-modal-text">
          Previewing This Page With Content Management System with Admin Permission
        </p>
        {expiryDisplay && <p className="cms-live-preview-modal-expiry">Expires at {expiryDisplay}</p>}
        <button
          type="button"
          className="itg-btn itg-btn-primary cms-live-preview-modal-close"
          onClick={() => setShowPreviewModal(false)}
        >
          OK
        </button>
      </div>
    </div>
  );
};
