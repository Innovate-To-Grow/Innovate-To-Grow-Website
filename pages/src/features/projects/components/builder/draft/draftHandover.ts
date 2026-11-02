import type {ProjectGridRow} from '../../grid/contracts/projectGrid';

/**
 * The Past Projects (or All Projects) widget on a partner's page is that route in a cross-site frame
 * (`/_embed/<slug>`). Browsers keep such a frame's storage apart from the site's own, so the widget's curation draft,
 * and any sign-in made in it, stay in the frame. Signing in and saving therefore happen on the full page, in a new
 * tab, and the draft's projects go along in that link's fragment (the part of a URL no server sees, so its length is
 * free).
 */
export const isEmbeddedBuilder = () => window.location.pathname.startsWith('/_embed/');

export const PAST_PROJECTS_PATH = '/past-projects';

const HANDOVER_KEY = 'curation-draft';
const PROJECT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** An archive Project's or an event CurrentProject's id (a UUID). */
export const isProjectId = (value: unknown): value is string => typeof value === 'string' && PROJECT_ID.test(value);

/**
 * The full builder page at `path` (the widget's route: Past Projects or All Projects), carrying the draft's projects
 * (by id) for that page to add to its own draft.
 */
export const draftHandoverHref = (rows: readonly Pick<ProjectGridRow, 'id'>[], path: string = PAST_PROJECTS_PATH) => {
  const ids = [...new Set(rows.flatMap((row) => (row.id ? [row.id] : [])))];
  return ids.length ? `${path}#${HANDOVER_KEY}=${ids.join(',')}` : path;
};

/** The project ids a widget handed over in a URL fragment (`#curation-draft=…`); null when it hands none over. */
export const readDraftHandover = (hash: string): string[] | null => {
  const value = new URLSearchParams(hash.replace(/^#/, '')).get(HANDOVER_KEY);
  return value === null ? null : [...new Set(value.split(',').filter(isProjectId))];
};
