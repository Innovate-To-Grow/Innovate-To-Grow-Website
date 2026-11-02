import './LoadingIndicator.css';

interface LoadingIndicatorProps {
  /** What is loading, as the visible text ("Loading project data…"). */
  label: string;
  className?: string;
}

/**
 * The site's one loading look: a 24px spinner beside a line of text. It carries no role: the element
 * that hosts it keeps its own `role="status"` (or live region), reserved height and focus ref.
 */
export const LoadingIndicator = ({label, className}: LoadingIndicatorProps) => (
  <span className={`loading-indicator${className ? ` ${className}` : ''}`}>
    <span className="loading-indicator-spinner" aria-hidden="true" />
    <span className="loading-indicator-label">{label}</span>
  </span>
);
