import {StatusAlert} from '../shared/StatusAlert';
import {useMySharedLinks} from './internal/useMySharedLinks';

export const MySharedLinksSection = () => {
  const {shares, loading, error, successMessage, handleDelete} = useMySharedLinks();

  // The section is absent for accounts that have never created a share.
  if (!loading && shares.length === 0) {
    return null;
  }

  return (
    <div className="account-section">
      <h2 className="account-section-title">My Shared Links</h2>

      {successMessage ? <StatusAlert tone="success" message={successMessage} style={{marginBottom: '1rem'}} /> : null}
      {error ? <StatusAlert tone="error" message={error} style={{marginBottom: '1rem'}} /> : null}

      {loading ? (
        <p className="account-status-text">Loading your shared links...</p>
      ) : (
        <ul className="account-shares-list">
          {shares.map((share) => (
            <li key={share.id} className="account-shares-item">
              <div className="account-shares-meta">
                <span className="account-shares-name">{share.name}</span>
                <span className="account-shares-sub">
                  {share.row_count} {share.row_count === 1 ? 'result' : 'results'} ·{' '}
                  {new Date(share.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="account-shares-actions">
                <a
                  className="account-outline-btn"
                  href={`/past-projects/${share.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open
                </a>
                <button
                  type="button"
                  className="account-shares-delete"
                  onClick={() => void handleDelete(share.id)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
