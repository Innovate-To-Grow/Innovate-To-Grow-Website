import type {PastProjectShareSummary} from '@/features/projects/api';
import {formatSharedLinkDate, getSharedLinkDisplayName, getSharedLinkResultsLabel} from './sharedLinkUtils';

interface SharedLinksListProps {
  shares: PastProjectShareSummary[];
  onDelete: (id: string) => void | Promise<void>;
}

export const SharedLinksList = ({shares, onDelete}: SharedLinksListProps) => (
  <ul className="account-shares-list">
    {shares.map((share) => {
      const name = getSharedLinkDisplayName(share);
      const details = `${getSharedLinkResultsLabel(share)} · ${formatSharedLinkDate(share.created_at)}`;
      // Unnamed shares all read "Past Project Curation", so the controls name the row they act on.
      const rowLabel = `${name} (${details})`;
      return (
        <li key={share.id} className="account-shares-item">
          <div className="account-shares-meta">
            <span className="account-shares-name">{name}</span>
            <span className="account-shares-sub">{details}</span>
          </div>
          <div className="account-shares-actions">
            <a
              className="account-outline-btn"
              href={`/past-projects/${share.id}`}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`Open ${rowLabel}`}
            >
              Open
            </a>
            <button
              type="button"
              className="account-shares-delete"
              aria-label={`Delete ${rowLabel}`}
              onClick={() => void onDelete(share.id)}
            >
              Delete
            </button>
          </div>
        </li>
      );
    })}
  </ul>
);
