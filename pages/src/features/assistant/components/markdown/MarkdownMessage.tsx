import {lazy, Suspense} from 'react';

// Lazy boundary: the impl statically imports react-markdown + remark-gfm, so
// both libraries land in a separate chunk and stay out of the entry bundle.
const MarkdownMessageImpl = lazy(() => import('./MarkdownMessageImpl'));

interface MarkdownMessageProps {
  content: string;
}

/**
 * Renders assistant message text as Markdown. While the markdown chunk loads,
 * the raw text is shown as a plain fallback so content is never blank.
 */
export function MarkdownMessage({content}: MarkdownMessageProps) {
  return (
    <Suspense fallback={<span className="itg-assistant__markdown-fallback">{content}</span>}>
      <MarkdownMessageImpl content={content} />
    </Suspense>
  );
}
