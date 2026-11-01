import {useEffect, type ReactNode} from 'react';
import {Link, useLocation, useParams} from 'react-router';
import {ProjectsMessagePage} from '@/features/projects/components/views/pages/ProjectsMessagePage';
import {useCopyLink} from '@/hooks/useCopyLink';
import {useProjectDetail, type ProjectDetailError} from '@/features/projects/hooks/useProjectDetail';
import {usePageTitle} from '@/hooks/usePageTitle';
import {ProjectDetailBody} from './ProjectDetailBody';
import {ProjectBackLink} from './ProjectBackLink';
import {resolveProjectBackTarget, type ProjectBackTarget} from './projectBackTarget';
import './ProjectDetailPage.css';

interface ProjectLoadFailedProps {
  error: string | null;
  backLink: ReactNode;
  retry: () => void;
}

/** A project that does not exist (or a link that is wrong), or one that could not be loaded right now. */
const ProjectLoadFailed = ({error, backLink, retry}: ProjectLoadFailedProps) => {
  const notFound = error !== 'failed';
  // Neither state belongs in search results; the mark goes with this message (a retry that loads the project).
  usePageTitle(null, {noindex: true});
  return (
    <ProjectsMessagePage
      className="project-detail projects-error"
      before={backLink}
      title={notFound ? "We couldn't find this project" : "We couldn't load this project"}
      actions={
        <>
          {notFound ? null : (
            <button type="button" className="itg-btn itg-btn-primary" onClick={retry}>
              Try again
            </button>
          )}
          <Link className={`itg-btn ${notFound ? 'itg-btn-primary' : 'itg-btn-outline'}`} to="/past-projects">
            Search past projects
          </Link>
          <Link className="itg-link" to="/current-projects">
            Current Projects
          </Link>
        </>
      }
    >
      <p>
        {notFound
          ? 'The link may be incomplete, or the project has been removed from the catalog. Search for it by title, team or organization.'
          : 'Unable to load this project. Please try again, or search for it by title, team or organization.'}
      </p>
    </ProjectsMessagePage>
  );
};

/** Back to the list, and copy a link to this project. */
const ProjectDetailActions = ({backTarget}: {backTarget: ProjectBackTarget}) => {
  const {status: copyStatus, copy} = useCopyLink({
    copied: 'Link copied.',
    failed: 'Could not copy the link. Copy it from the address bar instead.',
  });
  return (
    <div className="project-detail-actions">
      <ProjectBackLink target={backTarget} className="itg-link project-detail-actions-back">
        <span className="project-detail-wide-only" aria-hidden="true">
          ‹{' '}
        </span>
        <span>{backTarget.label}</span>
      </ProjectBackLink>
      <button
        type="button"
        className="itg-btn itg-btn-text project-detail-copy"
        onClick={() => void copy(window.location.href)}
      >
        <span>
          Copy link <span className="project-detail-wide-only">to this project</span>
        </span>
      </button>
      {copyStatus ? (
        <p className="project-detail-copy-status" role="status">
          {copyStatus}
        </p>
      ) : null}
    </div>
  );
};

/**
 * The tab's title: the project's, or what went wrong. None while the project loads: the tab keeps the last page's
 * title, which is what tells the page view sent to Siteimprove (usePageTracking) to wait for this page's own. A
 * section name here would read as this page's title to it whenever the visitor came from another section.
 */
const pageTitleFor = (projectTitle: string | undefined, error: ProjectDetailError | null) => {
  if (projectTitle) return projectTitle;
  if (error === 'failed') return "Project couldn't be loaded";
  return error ? 'Project not found' : null;
};

export const ProjectDetailPage = () => {
  const {id} = useParams<{id: string}>();
  const location = useLocation();
  const isPastProjectDetail = location.pathname.startsWith('/past-projects/project/');
  // /projects/:id is linked from Current Projects and Presenting Teams by this semester's schedule ids, and by
  // older links to archive projects: it looks in the current schedule first. Past-project pages read the archive.
  const {result, loading, error, retry} = useProjectDetail(id, !isPastProjectDetail);
  const backTarget = resolveProjectBackTarget(location.state, isPastProjectDetail || result?.source === 'archive');
  usePageTitle(pageTitleFor(result?.project.project_title, error));

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [id]);

  const backLink = (
    <ProjectBackLink target={backTarget} className="itg-back-link project-detail-back">
      <span>
        <span aria-hidden="true">‹ </span>
        {/* Its own element: the label can change once the project loads (an archive project goes back to Past
            Projects), and page translation would otherwise keep the old one. */}
        <span>{backTarget.label}</span>
      </span>
    </ProjectBackLink>
  );

  if (loading) {
    return (
      <div className="project-detail">
        <p className="itg-loading">Loading...</p>
      </div>
    );
  }

  if (error || !result) {
    return <ProjectLoadFailed error={error} backLink={backLink} retry={retry} />;
  }

  return (
    <article className="project-detail">
      {backLink}
      <ProjectDetailBody result={result} />
      <ProjectDetailActions backTarget={backTarget} />
    </article>
  );
};
