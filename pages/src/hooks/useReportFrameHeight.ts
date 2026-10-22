import {useEffect} from 'react';

/**
 * Inside an admin preview frame, posts the document height to the parent window so it can size the
 * frame: right away, after a few delays (late images and fonts) and on every resize. Nothing is
 * posted until there is ``content`` and a trusted ``targetOrigin``, or outside a frame. A change to
 * ``content`` or ``extra`` reports again.
 */
export function useReportFrameHeight(
  messageType: string,
  nonce: string,
  targetOrigin: string,
  content: unknown,
  extra: unknown = null,
): void {
  useEffect(() => {
    if (!content || !targetOrigin || window.parent === window) return;

    const reportHeight = () => {
      const height = Math.max(
        document.documentElement.scrollHeight,
        document.body ? document.body.scrollHeight : 0,
        document.documentElement.offsetHeight,
        document.body ? document.body.offsetHeight : 0,
      );
      if (height > 0) {
        window.parent.postMessage({type: messageType, nonce, height}, targetOrigin);
      }
    };

    reportHeight();
    const timers = [
      window.setTimeout(reportHeight, 100),
      window.setTimeout(reportHeight, 500),
      window.setTimeout(reportHeight, 1500),
    ];
    const resizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(reportHeight) : null;
    if (resizeObserver) {
      resizeObserver.observe(document.documentElement);
      if (document.body) resizeObserver.observe(document.body);
    }
    window.addEventListener('load', reportHeight);
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      resizeObserver?.disconnect();
      window.removeEventListener('load', reportHeight);
    };
  }, [content, extra, messageType, nonce, targetOrigin]);
}
