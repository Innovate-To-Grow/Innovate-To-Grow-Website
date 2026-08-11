import type {PastProjectShareSummary} from '@/features/projects/api';

export const PAST_PROJECT_CURATION_SHARED_LINKS_PATH = '/account/past-project-curation-shared-links';
export const PAST_PROJECT_CURATION_SHARED_LINKS_TITLE = 'Past Project Curation Shared Links';

export const formatSharedLinkDate = (value: string): string => new Date(value).toLocaleDateString();

export const getSharedLinkSearchText = (share: PastProjectShareSummary): string => [
  share.name,
  share.note,
  share.id,
  share.share_url,
  `${share.row_count}`,
  `${share.row_count} ${share.row_count === 1 ? 'result' : 'results'}`,
  formatSharedLinkDate(share.created_at),
].filter(Boolean).join(' ').toLowerCase();
