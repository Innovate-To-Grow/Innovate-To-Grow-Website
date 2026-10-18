import {useCallback, useEffect, useRef, useState} from 'react';

const STATUS_MS = 4000;

interface CopyLinkMessages {
  copied: string;
  failed: string;
}

/** Copies a link to the clipboard and reports the outcome for a role=status message that clears itself. */
export function useCopyLink({copied, failed}: CopyLinkMessages) {
  const [status, setStatus] = useState('');
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = useCallback(
    async (text: string) => {
      let ok = false;
      try {
        if (window.navigator.clipboard?.writeText) {
          await window.navigator.clipboard.writeText(text);
          ok = true;
        }
      } catch {
        // Report the failure below.
      }
      setStatus(ok ? copied : failed);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setStatus(''), STATUS_MS);
    },
    [copied, failed],
  );

  return {status, copy};
}
