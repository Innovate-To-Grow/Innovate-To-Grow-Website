import {Link} from 'react-router';
import {ProjectsMessagePage} from '@/features/projects/components/ProjectsMessagePage';

export const SharedListUnavailable = () => (
  <ProjectsMessagePage
    className="past-projects-share-unavailable"
    eyebrow="Shared list · Past Projects"
    title="This shared list isn't available"
    actions={
      <>
        <Link className="itg-btn itg-btn-primary" to="/past-projects">
          Search past projects
        </Link>
        <Link className="itg-link" to="/projects">
          Go to Projects
        </Link>
      </>
    }
  >
    <p>
      The link may be incomplete, or the person who shared it has deleted the list. Ask them to send the link again,
      or search the past projects yourself.
    </p>
  </ProjectsMessagePage>
);

/** The share request failed (server error, network, timeout): the link may be fine, so offer to try again. */
export const SharedListLoadFailed = ({onRetry}: {onRetry: () => void}) => (
  <ProjectsMessagePage
    className="past-projects-share-failed"
    eyebrow="Shared list · Past Projects"
    title="We couldn't load this shared list"
    actions={
      <>
        <button type="button" className="itg-btn itg-btn-primary" onClick={onRetry}>
          Try again
        </button>
        <Link className="itg-btn itg-btn-outline" to="/past-projects">
          Search past projects
        </Link>
      </>
    }
  >
    <p>Something went wrong while loading this list. Check your connection and try again.</p>
  </ProjectsMessagePage>
);
