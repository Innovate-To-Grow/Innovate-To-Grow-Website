import {Link} from 'react-router';
import {ProjectsMessagePage} from '@/features/projects/components/views/pages/ProjectsMessagePage';
import {softDisabled} from '@/features/projects/components/shared/utils/softDisabled';
import {usePageTitle} from '@/hooks/usePageTitle';

// Each names the tab after what happened, so a tab list or a screen reader's page title tells it from a curation.

export const SharedListUnavailable = () => {
  usePageTitle('Curation not available');
  return (
    <ProjectsMessagePage
      className="past-projects-share-unavailable"
      eyebrow="Curation · Past Projects"
      title="This curation isn't available"
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
        The link may be incomplete, or the person who shared it has deleted the curation. Ask them to send the link
        again, or search the past projects yourself.
      </p>
    </ProjectsMessagePage>
  );
};

interface SharedListLoadFailedProps {
  /** Try again was pressed and the curation is loading: the page stays (focus stays on the button) and says so. */
  retrying: boolean;
  onRetry: () => void;
}

/** The share request failed (server error, network, timeout): the link may be fine, so offer to try again. */
export const SharedListLoadFailed = ({retrying, onRetry}: SharedListLoadFailedProps) => {
  usePageTitle('Curation could not be loaded');
  return (
    <ProjectsMessagePage
      className="past-projects-share-failed"
      eyebrow="Curation · Past Projects"
      title="We couldn't load this curation"
      actions={
        <>
          <button type="button" className="itg-btn itg-btn-primary" {...softDisabled(retrying, onRetry)}>
            Try again
          </button>
          <Link className="itg-btn itg-btn-outline" to="/past-projects">
            Search past projects
          </Link>
        </>
      }
    >
      {/* A live region, so a retry's loading, and its failing again, are announced while the page stays. */}
      <p role="status">
        {retrying
          ? 'Loading curation...'
          : 'Something went wrong while loading this curation. Check your connection and try again.'}
      </p>
    </ProjectsMessagePage>
  );
};
