import {Link} from 'react-router';
import {LoadingIndicator} from '@/components/LoadingIndicator';
import {ProjectsMessagePage} from '@/features/projects/components/views/pages/ProjectsMessagePage';
import {softDisabled} from '@/features/projects/components/shared/utils/softDisabled';
import {usePageTitle} from '@/hooks/usePageTitle';

// Each names the tab after what happened, so a tab list or a screen reader's page title tells it from a curation.
// Neither knows which list the curation came from (it did not load), so the eyebrow is just "Curation" and the way
// on is All Projects, which searches both lists.

export const SharedListUnavailable = () => {
  usePageTitle('Curation not available');
  return (
    <ProjectsMessagePage
      className="past-projects-share-unavailable"
      eyebrow="Curation"
      title="This curation isn't available"
      actions={
        <>
          <Link className="itg-btn itg-btn-primary" to="/all-projects">
            Search All Projects
          </Link>
          <Link className="itg-link" to="/projects">
            Go to Projects
          </Link>
        </>
      }
    >
      <p>
        The link may be incomplete, or the person who shared it has deleted the curation. Ask them to send the link
        again, or search all projects yourself.
      </p>
    </ProjectsMessagePage>
  );
};

interface SharedListLoadFailedProps {
  /** Try Again was pressed and the curation is loading: the page stays (focus stays on the button) and says so. */
  retrying: boolean;
  onRetry: () => void;
}

/**
 * The share request failed (server error, network, timeout): the link may be fine, so Try Again is the page's one
 * primary action, and the other way on is a text link, as on the other message pages.
 */
export const SharedListLoadFailed = ({retrying, onRetry}: SharedListLoadFailedProps) => {
  usePageTitle('Curation could not be loaded');
  return (
    <ProjectsMessagePage
      className="past-projects-share-failed"
      eyebrow="Curation"
      title="We couldn't load this curation"
      actions={
        <>
          <button type="button" className="itg-btn itg-btn-primary" {...softDisabled(retrying, onRetry)}>
            Try Again
          </button>
          <Link className="itg-link" to="/all-projects">
            Search All Projects
          </Link>
        </>
      }
    >
      {/* A live region, so a retry's loading, and its failing again, are announced while the page stays. */}
      <p role="status">
        {retrying ? (
          <LoadingIndicator label="Loading curation…" />
        ) : (
          'Something went wrong while loading this curation. Check your connection and try again.'
        )}
      </p>
    </ProjectsMessagePage>
  );
};
