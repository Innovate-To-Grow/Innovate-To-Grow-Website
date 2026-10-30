import {useCallback, useEffect, useRef, useState} from 'react';

const STATUS_MS = 4000;

interface CopyLinkMessages {
  copied: string;
  failed: string;
}

/** Copies ``text`` from a selected, off-screen field; false when the browser refuses. */
function copyBySelection(text: string): boolean {
  if (typeof document.execCommand !== 'function') return false;
  const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const field = document.createElement('textarea');
  field.value = text;
  field.readOnly = true;
  field.style.position = 'fixed';
  field.style.left = '-9999px';
  document.body.appendChild(field);
  field.focus({preventScroll: true});
  field.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    // Report the failure.
  }
  field.remove();
  previousFocus?.focus({preventScroll: true});
  return ok;
}

/** Copies through the Clipboard API, else by selection (which embeds denied `clipboard-write` still allow). */
async function copyText(text: string): Promise<boolean> {
  try {
    if (window.navigator.clipboard?.writeText) {
      await window.navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall back to copying by selection.
  }
  return copyBySelection(text);
}

/** Copies a link to the clipboard and reports the outcome for a role=status message that clears itself. */
export function useCopyLink({copied, failed}: CopyLinkMessages) {
  const [status, setStatus] = useState('');
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = useCallback(
    async (text: string) => {
      const ok = await copyText(text);
      setStatus(ok ? copied : failed);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setStatus(''), STATUS_MS);
    },
    [copied, failed],
  );

  return {status, copy};
}
