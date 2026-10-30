import {useEffect, useRef} from 'react';
import {reloadPage} from '@/app/pageReload';

interface ErrorFallbackProps {
  /** h1 when the message stands in for a routed page; h2 inside the menu, footer or assistant roots. */
  headingLevel?: 'h1' | 'h2';
  title?: string;
  message?: string;
  reloadLabel?: string;
  className?: string;
  /** Moves focus to the heading, for a page that broke under the visitor's hands. */
  focusHeading?: boolean;
}

/**
 * The branded "something went wrong" message with a reload button and a link home. Plain links only:
 * it also renders outside the router. It never shows the error itself (no stack traces for visitors).
 */
export function ErrorFallback({
  headingLevel: Heading = 'h2',
  title = 'Something went wrong',
  message = 'Please refresh the page or try again later.',
  reloadLabel = 'Refresh',
  className = '',
  focusHeading = false,
}: ErrorFallbackProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (focusHeading) headingRef.current?.focus({preventScroll: true});
  }, [focusHeading]);

  return (
    <section className={`itg-empty-state ${className}`.trim()} role="alert">
      <Heading
        ref={headingRef}
        className={Heading === 'h1' ? 'itg-page-title' : 'itg-empty-state-title'}
        tabIndex={focusHeading ? -1 : undefined}
      >
        {title}
      </Heading>
      <p className="itg-empty-state-text">{message}</p>
      <div className="itg-empty-state-actions">
        <button type="button" className="itg-btn itg-btn-primary" onClick={reloadPage}>
          {reloadLabel}
        </button>
        <a href="/" className="itg-link">
          Go to the home page
        </a>
      </div>
    </section>
  );
}
