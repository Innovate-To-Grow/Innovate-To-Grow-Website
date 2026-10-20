import {useEffect, useState} from 'react';
import {Link} from 'react-router';
import {PAST_PROJECT_CURATION_SHARED_LINKS_PATH, useAuth} from '@/features/auth';
import {DEFAULT_PAST_PROJECT_SHARE_NAME, listMyShares, type PastProjectShareSummary} from '@/features/projects/api';
import {useCopyLink} from '@/features/projects/hooks/useCopyLink';
import {pluralize} from './saveResults';

// The most recently changed curations listed here; the account page lists them all.
const RECENT_CURATION_COUNT = 5;

const lastChanged = (share: PastProjectShareSummary) => share.updated_at || share.created_at;

const lastChangedTime = (share: PastProjectShareSummary) => Date.parse(lastChanged(share)) || 0;

const formatCurationDate = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric'});
};

/** The signed-in member's saved curations, newest change first, so they can be found again from Past Projects. */
export const MyCurationsPanel = () => {
  const {isAuthenticated, isInitializing, user} = useAuth();
  const memberId = isAuthenticated && !isInitializing ? (user?.member_uuid ?? null) : null;
  // Tagged with the member they were loaded for, so another account never sees them while its own load runs.
  const [loaded, setLoaded] = useState<{memberId: string; shares: PastProjectShareSummary[]} | null>(null);
  const {status: copyStatus, copy} = useCopyLink({
    copied: 'Link copied.',
    failed: 'Could not copy the link. Open the curation and copy its address instead.',
  });

  useEffect(() => {
    if (!memberId) {
      return;
    }
    let active = true;
    listMyShares()
      .then((shares) => {
        if (active) setLoaded({memberId, shares});
      })
      .catch(() => {
        // The builder works without the list; leave it out rather than show an error on every visit.
        if (active) setLoaded({memberId, shares: []});
      });
    return () => {
      active = false;
    };
  }, [memberId]);

  const shares = loaded && loaded.memberId === memberId ? loaded.shares : [];
  if (!shares.length) {
    return null;
  }

  const recent = [...shares]
    .sort((left, right) => lastChangedTime(right) - lastChangedTime(left))
    .slice(0, RECENT_CURATION_COUNT);

  return (
    <section className="itg-panel past-projects-my-curations" aria-labelledby="past-projects-my-curations-title">
      <div className="past-projects-my-curations-header">
        <h2 id="past-projects-my-curations-title" className="past-projects-my-curations-title">
          My Curations
        </h2>
        <Link className="itg-link" to={PAST_PROJECT_CURATION_SHARED_LINKS_PATH}>
          {shares.length > recent.length ? `See all ${shares.length}` : 'Manage curations'}
        </Link>
      </div>
      <p className="past-projects-my-curations-hint">Open a saved curation to view or edit it.</p>
      <ul className="past-projects-my-curations-list">
        {recent.map((share) => {
          const name = share.name.trim() || DEFAULT_PAST_PROJECT_SHARE_NAME;
          const date = formatCurationDate(lastChanged(share));
          return (
            <li key={share.id} className="past-projects-my-curation">
              <div className="past-projects-my-curation-meta">
                <Link className="past-projects-my-curation-name" to={`/past-projects/${share.id}`}>
                  {name}
                </Link>
                <span className="past-projects-my-curation-sub">
                  {pluralize(share.row_count, 'project')}
                  {date ? ` · ${share.updated_at ? 'updated' : 'saved'} ${date}` : ''}
                </span>
              </div>
              <button
                type="button"
                className="itg-btn itg-btn-text past-projects-my-curation-copy"
                aria-label={`Copy the link to ${name}`}
                onClick={() => void copy(share.share_url || `${window.location.origin}/past-projects/${share.id}`)}
              >
                Copy link
              </button>
            </li>
          );
        })}
      </ul>
      <p className="past-projects-my-curations-status" role="status">
        {copyStatus}
      </p>
    </section>
  );
};
