import {useCopyLink} from '../../hooks/useCopyLink';
import {useProjectGridDetails} from '../../hooks/useProjectGridDetails';
import {getProjectGridRowHref, type ProjectGridLinkScope, type ProjectGridRow} from '../projectGrid';
import {ProjectPageLink} from './ProjectTitleWithChips';

interface ProjectGridRowDetailsProps {
  row: ProjectGridRow;
  scope: ProjectGridLinkScope;
  loadMissingDetails?: boolean;
}

/** Copies the project's page URL; past-project rows offer it so a single project can be passed on. */
const CopyProjectLinkButton = ({href}: {href: string}) => {
  const {status, copy} = useCopyLink({
    copied: 'Project link copied.',
    failed: 'Could not copy the link. Use Open the project page and copy its address.',
  });

  return (
    <>
      <button type="button" className="itg-btn itg-btn-text project-grid-copy-link" onClick={() => void copy(href)}>
        Copy project link
      </button>
      {status ? (
        <span className="project-grid-copy-status" role="status">
          {status}
        </span>
      ) : null}
    </>
  );
};

export function ProjectGridRowDetails({row, scope, loadMissingDetails = false}: ProjectGridRowDetailsProps) {
  const href = getProjectGridRowHref(row, scope);
  const {details, loading, error, loaded, retry} = useProjectGridDetails(row, loadMissingDetails);

  return (
    <>
      {loading ? (
        <p className="project-grid-detail-state" role="status">
          Loading project details...
        </p>
      ) : null}
      {error ? (
        <p className="project-grid-detail-state itg-error" role="alert">
          Unable to load project details.{' '}
          <button type="button" className="itg-btn itg-btn-text" onClick={retry}>
            Retry
          </button>
        </p>
      ) : null}
      {details.abstract ? <p className="project-grid-detail-abstract">{details.abstract}</p> : null}
      {details.student_names ? (
        <p className="project-grid-detail-members">
          <strong>Team members:</strong> {details.student_names}
        </p>
      ) : null}
      {loaded && !details.abstract && !details.student_names ? (
        <p className="project-grid-detail-state">No abstract or student names available.</p>
      ) : null}
      {href ? (
        <div className="project-grid-detail-links">
          <ProjectPageLink className="project-grid-individual-link" href={href} scope={scope}>
            Open the project page
          </ProjectPageLink>
          {scope === 'past' ? <CopyProjectLinkButton href={href} /> : null}
        </div>
      ) : null}
    </>
  );
}
