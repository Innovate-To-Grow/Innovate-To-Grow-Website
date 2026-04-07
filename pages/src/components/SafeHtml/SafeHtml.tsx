import {useMemo} from 'react';
import DOMPurify from 'dompurify';

const SANITIZE_OPTIONS = {
  USE_PROFILES: {html: true},
  ADD_ATTR: ['target', 'rel', 'aria-label'],
};

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
