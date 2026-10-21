import {useId, useRef, type ReactNode} from 'react';

interface SharedLinkPanelProps {
  shareUrl: string;
  onStatus: (message: string) => void;
  /** Shown beside the link (the export buttons). */
  children: ReactNode;
}

/** Copies through the Clipboard API, then the selected-input `execCommand` fallback, then asks the user. */
async function copyShareUrl(shareUrl: string, input: HTMLInputElement, onStatus: (message: string) => void) {
  input.select();

  try {
    if (window.navigator.clipboard?.writeText) {
      await window.navigator.clipboard.writeText(shareUrl);
      onStatus('Shareable URL copied.');
      return;
    }
  } catch {
    // Fall through to the selected-input copy fallback below.
  }

  try {
    if (document.execCommand('copy')) {
      onStatus('Shareable URL copied.');
      return;
    }
  } catch {
    // Keep the final fallback message below.
  }

  onStatus('Unable to copy URL. Select the link and copy it manually.');
}

/** Shared page: the link to pass on, with a Copy button and the exports beside it. */
export const SharedLinkPanel = ({shareUrl, onStatus, children}: SharedLinkPanelProps) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();

  return (
    <div className="itg-panel project-grid-share-result">
      <div className="itg-field project-grid-share-result-field">
        <label className="project-grid-field-label" htmlFor={inputId}>
          Shareable link
        </label>
        <div className="project-grid-share-result-row">
          <input
            ref={inputRef}
            id={inputId}
            type="text"
            className="itg-input project-grid-share-result-input"
            value={shareUrl}
            readOnly
            title="Click to copy the link"
            onFocus={(event) => {
              void copyShareUrl(shareUrl, event.currentTarget, onStatus);
            }}
            onClick={(event) => {
              void copyShareUrl(shareUrl, event.currentTarget, onStatus);
            }}
          />
          <button
            type="button"
            className="itg-btn itg-btn-primary project-grid-share-copy"
            onClick={() => {
              if (inputRef.current) void copyShareUrl(shareUrl, inputRef.current, onStatus);
            }}
          >
            Copy link
          </button>
        </div>
      </div>
      {children}
    </div>
  );
};
