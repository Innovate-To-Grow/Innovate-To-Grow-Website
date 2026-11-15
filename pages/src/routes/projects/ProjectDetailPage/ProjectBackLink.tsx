import type {MouseEvent, ReactNode} from 'react';
import {Link, useNavigate} from 'react-router';
import type {ProjectBackTarget} from './projectBackTarget';

const opensElsewhere = (event: MouseEvent) =>
  event.button !== 0 || event.metaKey || event.altKey || event.ctrlKey || event.shiftKey;

interface ProjectBackLinkProps {
  target: ProjectBackTarget;
  className: string;
  children: ReactNode;
}

/**
 * The back link. When the list opened this page it goes back in history, so the list comes back where the visitor
 * left it, scroll included; a new tab (or a page opened from elsewhere) follows the link.
 */
export const ProjectBackLink = ({target, className, children}: ProjectBackLinkProps) => {
  const navigate = useNavigate();
  const goBack = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!target.openedFromList || opensElsewhere(event)) return;
    event.preventDefault();
    void navigate(-1);
  };
  return (
    <Link to={target.href} className={className} onClick={goBack}>
      {children}
    </Link>
  );
};
