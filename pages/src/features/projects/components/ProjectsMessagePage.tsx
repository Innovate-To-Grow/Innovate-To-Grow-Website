import './projects.css';
import type {ReactNode} from 'react';

interface ProjectsMessagePageProps {
  /** Above the title, e.g. a back link. */
  before?: ReactNode;
  eyebrow?: string;
  title: string;
  children: ReactNode;
  actions: ReactNode;
  className?: string;
}

/** A page-level empty or error state (unavailable share link, project not found), per the States draft. */
export const ProjectsMessagePage = ({before, eyebrow, title, children, actions, className}: ProjectsMessagePageProps) => (
  <section className={`itg-empty-state projects-message-page${className ? ` ${className}` : ''}`}>
    {before}
    <div>
      {eyebrow ? <p className="itg-eyebrow">{eyebrow}</p> : null}
      <h1 className="itg-page-title">{title}</h1>
    </div>
    <div className="itg-empty-state-text">{children}</div>
    <div className="itg-empty-state-actions">{actions}</div>
  </section>
);
