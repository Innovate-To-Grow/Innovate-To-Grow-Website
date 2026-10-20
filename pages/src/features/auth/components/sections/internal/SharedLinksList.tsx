import type {PastProjectShareSummary} from '@/features/projects/api';
import {useCopyLink} from '@/features/projects/hooks/useCopyLink';
import {formatSharedLinkDate, getSharedLinkDisplayName, getSharedLinkResultsLabel} from './sharedLinkUtils';

interface SharedLinksListProps {
  shares: PastProjectShareSummary[];
  onDelete: (id: string) => void | Promise<void>;
}

const shareLink = (share: PastProjectShareSummary): string =>
  share.share_url || `${window.location.origin}/past-projects/${share.id}`;

export const SharedLinksList = ({shares, onDelete}: SharedLinksListProps) => {
  const {status: copyStatus, copy} = useCopyLink({
    copied: 'Link copied.',
    failed: 'Could not copy the link. Open it and copy the address instead.',
  });

  return (
    <>
      <ul className="account-shares-list">
        {shares.map((share) => {
          const name = getSharedLinkDisplayName(share);
          const details = `${getSharedLinkResultsLabel(share)} · ${formatSharedLinkDate(share.updated_at || share.created_at)}`;
          // Unnamed shares all read "Past Project Curation", so the controls name the row they act on.
          const rowLabel = `${name} (${details})`;
          return (
            <li key={share.id} className="account-shares-item">
              <div className="account-shares-meta">
                <span className="account-shares-name">{name}</span>
                <span className="account-shares-sub">{details}</span>
              </div>
              <div className="account-shares-actions">
                <button
                  type="button"
                  className="itg-btn itg-btn-outline account-outline-btn"
                  aria-label={`Copy the link to ${rowLabel}`}
                  onClick={() => void copy(shareLink(share))}
                >
                  Copy link
                </button>
                <a
                  className="itg-btn itg-btn-outline account-outline-btn"
                  href={`/past-projects/${share.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`Open ${rowLabel}`}
                >
                  Open
                </a>
                <button
                  type="button"
                  className="itg-btn itg-btn-danger account-shares-delete"
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
      <p className="account-shares-copy-status" role="status">{copyStatus}</p>
    </>
  );
};
