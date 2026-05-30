import {memo, useEffect, useMemo, useRef} from 'react';
import DOMPurify from 'dompurify';

const ALLOWED_IFRAME_HOSTS = ['www.youtube.com', 'youtube.com', 'www.youtube-nocookie.com', 'player.vimeo.com'];

const SANITIZE_OPTIONS = {
  USE_PROFILES: {html: true},
  ADD_TAGS: ['iframe'],
  ADD_ATTR: ['target', 'rel', 'aria-label', 'allow', 'allowfullscreen', 'frameborder'],
};

// Remove iframes whose src does not point to a trusted video host
DOMPurify.addHook('uponSanitizeElement', (node, data) => {
  if (data.tagName === 'iframe' && node instanceof Element) {
    const src = node.getAttribute('src') || '';
    try {
      const url = new URL(src);
      if (!ALLOWED_IFRAME_HOSTS.includes(url.hostname)) {
        node.remove();
      }
    } catch {
      node.remove();
    }
  }
});

interface SafeHtmlProps {
  html: string;
  className?: string;
}

export const SafeHtml = memo(({html, className}: SafeHtmlProps) => {
  const ref = useRef<HTMLDivElement>(null);
  const sanitizedHtml = useMemo(
    () => DOMPurify.sanitize(html, SANITIZE_OPTIONS),
    [html],
  );

  // Set innerHTML via ref so the DOM (including iframes) is only replaced
  // when the sanitized HTML actually changes — not on every parent re-render.
  useEffect(() => {
    if (ref.current) {
      ref.current.innerHTML = sanitizedHtml;
    }
  }, [sanitizedHtml]);

  return <div ref={ref} className={className} />;
});
