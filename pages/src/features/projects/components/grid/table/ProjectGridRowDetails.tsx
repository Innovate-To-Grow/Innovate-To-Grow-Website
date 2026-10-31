import {useCopyLink} from '@/hooks/useCopyLink';
import {useProjectGridDetails} from '../../../hooks/useProjectGridDetails';
import {getProjectGridRowHref, type ProjectGridLinkScope, type ProjectGridRow} from '../contracts/projectGrid';
import {ProjectPageLink} from './ProjectTitleWithChips';

interface ProjectGridRowDetailsProps {
  row: ProjectGridRow;
  scope: ProjectGridLinkScope;
  loadMissingDetails?: boolean;
  /**
   * Loading and load errors are status messages. Off when View All Details opened every row at once: a screen
   * reader would hear one message per row, so the grid says it once instead.
   */
  announce?: boolean;
}

/** Copies the project's page URL; past-project rows offer it so a single project can be passed on. */
const CopyProjectLinkButton = ({href, title}: {href: string; title: string}) => {
  const {status, copy} = useCopyLink({
    copied: 'Project link copied.',
    failed: 'Could not copy the link. Use Open the Project Page and copy its address.',
  });

  return (
    <>
      <button type="button" className="itg-btn itg-btn-text project-grid-copy-link" onClick={() => void copy(href)}>
        Copy Project Link{' '}
        <span className="sr-only">{`for ${title}`}</span>
      </button>
      {status ? (
        <span className="project-grid-copy-status" role="status">
          {status}
        </span>
      ) : null}
    </>
  );
};

export function ProjectGridRowDetails({row, scope, loadMissingDetails = false, announce = true}: ProjectGridRowDetailsProps) {
  const href = getProjectGridRowHref(row, scope);
  const {details, loading, error, loaded, retry} = useProjectGridDetails(row, loadMissingDetails);

  return (
    <>
      {loading ? (
        <p className="project-grid-detail-state" role={announce ? 'status' : undefined}>
          Loading project details...
        </p>
      ) : null}
      {error ? (
        <p className="project-grid-detail-state itg-error" role={announce ? 'alert' : undefined}>
          Unable to load project details.{' '}
          <button type="button" className="itg-btn itg-btn-text" onClick={retry}>
            Retry
          </button>
        </p>
      ) : null}
      {details.abstract ? <p className="project-grid-detail-abstract">{details.abstract}</p> : null}
      {details.student_names ? (
        <p className="project-grid-detail-members">
          <strong>Team members:</strong> <span>{details.student_names}</span>
        </p>
      ) : null}
      {loaded && !details.abstract && !details.student_names ? (
        <p className="project-grid-detail-state">No abstract or student names available.</p>
      ) : null}
      {href ? (
        <div className="project-grid-detail-links">
          {/* Named after the project, so a list of the page's links tells them apart. */}
          <ProjectPageLink className="project-grid-individual-link" href={href} scope={scope}>
            Open the Project Page{' '}
            <span className="sr-only">{`for ${row.project_title}`}</span>
          </ProjectPageLink>
          {scope === 'past' ? <CopyProjectLinkButton href={href} title={row.project_title} /> : null}
        </div>
      ) : null}
    </>
  );
}
