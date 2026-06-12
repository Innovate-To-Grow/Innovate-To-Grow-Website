import {StatusAlert} from '../shared/StatusAlert';
import {useMySharedLinks} from './internal/useMySharedLinks';
import {
  PAST_PROJECT_CURATION_SHARED_LINKS_PATH,
  PAST_PROJECT_CURATION_SHARED_LINKS_TITLE,
} from './internal/sharedLinkUtils';
import {SharedLinksList} from './internal/SharedLinksList';

export const MySharedLinksSection = () => {
  const {shares, loading, error, successMessage, handleDelete} = useMySharedLinks();

  // The section is absent for accounts that have never created a share.
  if (!loading && shares.length === 0) {
    return null;
  }

  return (
    <div className="account-section">
      <div className="account-shares-header">
        <h2 className="account-section-title">{PAST_PROJECT_CURATION_SHARED_LINKS_TITLE}</h2>
        <a className="account-outline-btn account-shares-page-link" href={PAST_PROJECT_CURATION_SHARED_LINKS_PATH}>
          View Full Page
        </a>
      </div>

      {successMessage ? <StatusAlert tone="success" message={successMessage} style={{marginBottom: '1rem'}} /> : null}
      {error ? <StatusAlert tone="error" message={error} style={{marginBottom: '1rem'}} /> : null}

      {loading ? (
        <p className="account-status-text">Loading your shared links...</p>
      ) : (
        <SharedLinksList shares={shares} onDelete={handleDelete} />
      )}
    </div>
  );
};
