import {useMemo, useState} from 'react';
import {Navigate} from 'react-router-dom';
import {buildCompleteProfilePath, buildLoginPath} from '@/features/auth/api/redirects';
import {useAuth} from '../AuthContext';
import {StatusAlert} from '../shared/StatusAlert';
import {
  getSharedLinkSearchText,
  PAST_PROJECT_CURATION_SHARED_LINKS_PATH,
  PAST_PROJECT_CURATION_SHARED_LINKS_TITLE,
} from '../sections/internal/sharedLinkUtils';
import {SharedLinksList} from '../sections/internal/SharedLinksList';
import {useMySharedLinks} from '../sections/internal/useMySharedLinks';

export const PastProjectCurationSharedLinksPage = () => {
  const {isAuthenticated, requiresProfileCompletion} = useAuth();
  const canLoadShares = isAuthenticated && !requiresProfileCompletion;
  const {shares, loading, error, successMessage, handleDelete} = useMySharedLinks(canLoadShares, true);
  const [query, setQuery] = useState('');

  const normalizedQuery = query.trim().toLowerCase();
  const filteredShares = useMemo(() => {
    if (!normalizedQuery) return shares;
    return shares.filter((share) => getSharedLinkSearchText(share).includes(normalizedQuery));
  }, [normalizedQuery, shares]);

  if (!isAuthenticated) {
    return <Navigate to={buildLoginPath(PAST_PROJECT_CURATION_SHARED_LINKS_PATH)} replace />;
  }

  if (requiresProfileCompletion) {
    return <Navigate to={buildCompleteProfilePath(PAST_PROJECT_CURATION_SHARED_LINKS_PATH)} replace />;
  }

  return (
    <div className="account-page account-shared-links-page">
      <div className="account-shared-links-page-header">
        <h1 className="account-page-title">{PAST_PROJECT_CURATION_SHARED_LINKS_TITLE}</h1>
        <a className="account-outline-btn account-shared-links-back" href="/account">
          Back to Account
        </a>
      </div>

      <div className="account-section account-shared-links-section">
        {successMessage ? <StatusAlert tone="success" message={successMessage} style={{marginBottom: '1rem'}} /> : null}
        {error ? <StatusAlert tone="error" message={error} style={{marginBottom: '1rem'}} /> : null}

        <div className="account-shared-links-toolbar">
          <label className="auth-form-label" htmlFor="past-project-curation-shared-links-search">
            Search Shared Links
          </label>
          <input
            id="past-project-curation-shared-links-search"
            className="auth-form-input account-shared-links-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by name, note, URL, ID, result count, or date"
          />
          {!loading ? (
            <p className="account-status-text account-shared-links-count">
              {filteredShares.length} of {shares.length} shared links
            </p>
          ) : null}
        </div>

        {loading ? (
          <p className="account-status-text">Loading your shared links...</p>
        ) : error && shares.length === 0 ? (
          null
        ) : shares.length === 0 ? (
          <p className="account-status-text">No Past Project Curation Shared Links yet.</p>
        ) : filteredShares.length === 0 ? (
          <p className="account-status-text">No shared links match your search.</p>
        ) : (
          <SharedLinksList shares={filteredShares} onDelete={handleDelete} />
        )}
      </div>
    </div>
  );
};
