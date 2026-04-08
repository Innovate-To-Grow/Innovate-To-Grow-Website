import {useMemo} from 'react';
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

export const SafeHtml = ({html, className}: SafeHtmlProps) => {
  const sanitizedHtml = useMemo(
    () => DOMPurify.sanitize(html, SANITIZE_OPTIONS),
    [html],
  );

  return <div className={className} dangerouslySetInnerHTML={{__html: sanitizedHtml}} />;
};
