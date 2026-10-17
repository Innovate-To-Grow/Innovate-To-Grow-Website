import {DEFAULT_PAST_PROJECT_SHARE_NAME, type PastProjectShareSummary} from '@/features/projects/api';

export const PAST_PROJECT_CURATION_SHARED_LINKS_PATH = '/account/past-project-curation-shared-links';
export const PAST_PROJECT_CURATION_SHARED_LINKS_TITLE = 'Past Project Curation Shared Links';

export const formatSharedLinkDate = (value: string): string => new Date(value).toLocaleDateString();

/** The title the shared page shows; legacy shares may be stored without a name. */
export const getSharedLinkDisplayName = (share: PastProjectShareSummary): string =>
  share.name.trim() || DEFAULT_PAST_PROJECT_SHARE_NAME;

export const getSharedLinkResultsLabel = (share: PastProjectShareSummary): string =>
  `${share.row_count} ${share.row_count === 1 ? 'result' : 'results'}`;

export const getSharedLinkSearchText = (share: PastProjectShareSummary): string => [
  getSharedLinkDisplayName(share),
  share.note,
  share.id,
  share.share_url,
  `${share.row_count}`,
  getSharedLinkResultsLabel(share),
  formatSharedLinkDate(share.created_at),
].filter(Boolean).join(' ').toLowerCase();
