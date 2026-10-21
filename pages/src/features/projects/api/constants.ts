// Dependency-free so modules outside the projects feature (the auth account pages) can read it without
// importing the projects API client.

/**
 * Title of a share saved without a name or any note text of the owner's own. Mirrors the backend
 * default (src/apps/projects/services/share_names.py DEFAULT_SHARE_NAME); also the display fallback for
 * legacy shares stored with a blank name.
 */
export const DEFAULT_PAST_PROJECT_SHARE_NAME = 'Past Project Curation';
