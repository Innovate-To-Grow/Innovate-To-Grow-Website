import {useEffect, useId, useRef, useState, type ReactNode} from 'react';

const STATUS_MS = 4000;
const COPIED = 'Shareable URL copied.';
const COPY_FAILED = 'Unable to copy URL. Select the link and copy it manually.';

type CopyTone = 'success' | 'error';

interface SharedLinkPanelProps {
  shareUrl: string;
  /** Shown beside the link (the export buttons). */
  children: ReactNode;
}

/**
 * Copies through the Clipboard API, then the selected-input `execCommand` fallback. The visible link is selected
 * first, so when both fail it is already selected for the manual copy the failure asks for.
 */
async function copyShareUrl(shareUrl: string, input: HTMLInputElement): Promise<CopyTone> {
  input.select();

  try {
    if (window.navigator.clipboard?.writeText) {
      await window.navigator.clipboard.writeText(shareUrl);
      return 'success';
    }
  } catch {
    // Fall through to the selected-input copy fallback below.
  }

  try {
    if (document.execCommand('copy')) {
      return 'success';
    }
  } catch {
    // Report the failure below.
  }

  return 'error';
}

/** The panel's own copy feedback, cleared after four seconds (as useCopyLink's), and on unmount. */
function useCopyStatus() {
  const [status, setStatus] = useState<{message: string; tone: CopyTone | ''}>({message: '', tone: ''});
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const report = (tone: CopyTone) => {
    setStatus({message: tone === 'success' ? COPIED : COPY_FAILED, tone});
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setStatus({message: '', tone: ''}), STATUS_MS);
  };

  return {...status, report};
}

/** Shared page: the link to pass on, with a Copy Link button, the exports beside it and the copy's outcome. */
export const SharedLinkPanel = ({shareUrl, children}: SharedLinkPanelProps) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const {message, tone, report} = useCopyStatus();
  const copy = async (input: HTMLInputElement) => report(await copyShareUrl(shareUrl, input));

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
            // Taking focus only selects the link: tabbing through the page must not overwrite the clipboard.
            onFocus={(event) => event.currentTarget.select()}
            onClick={(event) => {
              void copy(event.currentTarget);
            }}
          />
          <button
            type="button"
            className="itg-btn itg-btn-primary project-grid-share-copy"
            onClick={() => {
              if (inputRef.current) void copy(inputRef.current);
            }}
          >
            Copy Link
          </button>
        </div>
      </div>
      {children}
      {/* In the page while empty, so its first message is announced too; it takes no room until it has one. */}
      <p className={`project-grid-share-copy-status ${tone === 'error' ? 'itg-error' : 'itg-success'}`} role="status">
        {message}
      </p>
    </div>
  );
};
