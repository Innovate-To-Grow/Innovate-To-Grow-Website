import type {PastProjectShareSummary} from '@/features/projects/api';
import {formatSharedLinkDate} from './sharedLinkUtils';

interface SharedLinksListProps {
  shares: PastProjectShareSummary[];
  onDelete: (id: string) => void | Promise<void>;
}

export const SharedLinksList = ({shares, onDelete}: SharedLinksListProps) => (
  <ul className="account-shares-list">
    {shares.map((share) => (
      <li key={share.id} className="account-shares-item">
        <div className="account-shares-meta">
          <span className="account-shares-name">{share.name}</span>
          <span className="account-shares-sub">
            {share.row_count} {share.row_count === 1 ? 'result' : 'results'} · {formatSharedLinkDate(share.created_at)}
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
            onClick={() => void onDelete(share.id)}
          >
            Delete
          </button>
        </div>
      </li>
    ))}
  </ul>
);
