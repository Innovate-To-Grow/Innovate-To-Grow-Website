import type {ProjectGridRow} from '../../grid/contracts/projectGrid';

/**
 * The Past Projects widget on a partner's page is this route in a cross-site frame (`/_embed/<slug>`). Browsers
 * keep such a frame's storage apart from the site's own, so the widget's curation draft, and any sign-in made in
 * it, stay in the frame. Signing in and saving therefore happen on the full Past Projects page, in a new tab, and
 * the draft's projects go along in that link's fragment (the part of a URL no server sees, so its length is free).
 */
export const isEmbeddedBuilder = () => window.location.pathname.startsWith('/_embed/');

export const PAST_PROJECTS_PATH = '/past-projects';

const HANDOVER_KEY = 'curation-draft';
const PROJECT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** The full Past Projects page, carrying the draft's projects (by id) for that page to add to its own draft. */
export const draftHandoverHref = (rows: readonly Pick<ProjectGridRow, 'id'>[]) => {
  const ids = [...new Set(rows.flatMap((row) => (row.id ? [row.id] : [])))];
  return ids.length ? `${PAST_PROJECTS_PATH}#${HANDOVER_KEY}=${ids.join(',')}` : PAST_PROJECTS_PATH;
};

/** The project ids a widget handed over in a URL fragment (`#curation-draft=…`); null when it hands none over. */
export const readDraftHandover = (hash: string): string[] | null => {
  const value = new URLSearchParams(hash.replace(/^#/, '')).get(HANDOVER_KEY);
  return value === null ? null : [...new Set(value.split(',').filter((id) => PROJECT_ID.test(id)))];
};
