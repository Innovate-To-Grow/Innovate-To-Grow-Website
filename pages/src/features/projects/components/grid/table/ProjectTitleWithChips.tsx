import type {ReactNode} from 'react';
import {Link, useInRouterContext, useLocation} from 'react-router';
import {
  getProjectGridRowHref,
  type ProjectGridLinkScope,
  type ProjectGridRow,
  type ProjectPageLinkState,
} from '../contracts/projectGrid';

interface ProjectPageLinkProps {
  href: string;
  scope: ProjectGridLinkScope;
  className?: string;
  children: ReactNode;
}

/** A client-side link that tells the project page which list (and which view of it) it was opened from. */
const RouterProjectLink = ({href, className, children}: Omit<ProjectPageLinkProps, 'scope'>) => {
  const {pathname, search} = useLocation();
  const state: ProjectPageLinkState = {from: `${pathname}${search}`};
  return (
    <Link className={className} to={href} state={state}>
      {children}
    </Link>
  );
};

/**
 * Link to a project page. Past-project links open in a new tab, so a curation in progress on the page is kept;
 * current-project links navigate in place (client-side when a router is present), and the project page's back
 * link returns to the list they came from.
 */
export const ProjectPageLink = ({href, scope, className, children}: ProjectPageLinkProps) => {
  const inRouter = useInRouterContext();
  if (scope === 'past') {
    return (
      <a className={className} href={href} target="_blank" rel="noopener noreferrer">
        {/* The space is its own text node: a hidden span's leading space is dropped from the link's name. */}
        {children}{' '}
        <span className="sr-only">(opens in a new tab)</span>
      </a>
    );
  }
  return inRouter ? (
    <RouterProjectLink className={className} href={href}>
      {children}
    </RouterProjectLink>
  ) : (
    <a className={className} href={href}>
      {children}
    </a>
  );
};

interface ProjectTitleWithChipsProps {
  row: ProjectGridRow;
  scope: ProjectGridLinkScope;
  /** Added by the latest save (merged results). */
  isNew: boolean;
  /** Already in the saved results (search tables). */
  isSaved: boolean;
  savedRowLabel: string;
}

// The title keeps its own text node so it can still be found by its exact text when tags follow it.
export const ProjectTitleWithChips = ({row, scope, isNew, isSaved, savedRowLabel}: ProjectTitleWithChipsProps) => {
  const href = getProjectGridRowHref(row, scope);
  return (
    <span className="project-grid-title-line">
      {href ? (
        <ProjectPageLink className="project-grid-title project-grid-title-link" href={href} scope={scope}>
          <span className="project-grid-title-text">{row.project_title}</span>
        </ProjectPageLink>
      ) : (
        <span className="project-grid-title">{row.project_title}</span>
      )}
      {isNew ? <span className="itg-tag itg-tag-new project-grid-row-chip is-new">New</span> : null}
      {isSaved ? <span className="itg-tag itg-tag-saved project-grid-row-chip is-saved">{savedRowLabel}</span> : null}
    </span>
  );
};
