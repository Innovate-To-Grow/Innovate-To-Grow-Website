// Dependency-free so modules outside the projects feature (the auth account pages) can read it without
// importing the projects API client.

/**
 * Title of a share saved without a name or any note text of the owner's own. Mirrors the backend
 * default (src/apps/projects/services/share_names.py DEFAULT_SHARE_NAME); also the display fallback for
 * legacy shares stored with a blank name.
 */
export const DEFAULT_PAST_PROJECT_SHARE_NAME = 'Past Project Curation';

/**
 * The same title for a share holding a current-semester project (a row with `catalog: 'current'`), which is not a
 * list of past projects. Mirrors share_names.py DEFAULT_PROJECT_SHARE_NAME; curationBranding picks between the two.
 */
export const DEFAULT_PROJECT_SHARE_NAME = 'Project Curation';

/**
 * How long one projects API request may take before it fails like a network error. The shared client sets no
 * timeout, so without one a stalled request leaves a list "Loading…" (or a row's details queued) indefinitely.
 */
export const PROJECT_REQUEST_TIMEOUT_MS = 15_000;
