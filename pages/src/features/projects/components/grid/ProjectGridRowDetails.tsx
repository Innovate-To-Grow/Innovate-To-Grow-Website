import {useProjectGridDetails} from '../../hooks/useProjectGridDetails';
import {getPastProjectDetailUrl, type ProjectGridRow} from '../projectGrid';

interface ProjectGridRowDetailsProps {
  row: ProjectGridRow;
  loadMissingDetails?: boolean;
}

export function ProjectGridRowDetails({row, loadMissingDetails = false}: ProjectGridRowDetailsProps) {
  const individualHref = row.id ? getPastProjectDetailUrl(row.id) : '';
  const {details, loading, error, loaded, retry} = useProjectGridDetails(row, loadMissingDetails);

  return (
    <>
      {individualHref ? (
        <div className="project-grid-individual-link-row">
          <span className="project-grid-individual-link-label">Individual Project URL</span>
          <a className="project-grid-individual-link" href={individualHref} target="_blank" rel="noopener noreferrer">
            {individualHref}
          </a>
        </div>
      ) : null}
      {loading ? <div role="status">Loading project details...</div> : null}
      {error ? (
        <div role="alert">
          Unable to load project details.{' '}
          <button type="button" className="project-grid-detail-button" onClick={retry}>Retry</button>
        </div>
      ) : null}
      {details.abstract ? <div><strong>Abstract:</strong> {details.abstract}</div> : null}
      {details.student_names ? <div><strong>Student Names:</strong> {details.student_names}</div> : null}
      {loaded && !details.abstract && !details.student_names ? <div>No abstract or student names available.</div> : null}
    </>
  );
}
