import {useEffect, useMemo, useRef} from 'react';

import {markMemberNoteLinks, sanitizePastProjectsDetailHtml} from './pastProjectsDetailText';

interface RichDetailPreviewProps {
  html: string;
  className?: string;
}

/**
 * Read-only render of sanitized rich-text HTML (used to show a saved curation note to visitors). A member wrote
 * it, so its links to other sites are marked nofollow / ugc.
 */
export function RichDetailPreview({html, className}: RichDetailPreviewProps) {
  const ref = useRef<HTMLDivElement>(null);
  const sanitizedHtml = useMemo(() => markMemberNoteLinks(sanitizePastProjectsDetailHtml(html)), [html]);

  useEffect(() => {
    if (ref.current) {
      ref.current.innerHTML = sanitizedHtml;
    }
  }, [sanitizedHtml]);

  return <div ref={ref} className={className} />;
}
