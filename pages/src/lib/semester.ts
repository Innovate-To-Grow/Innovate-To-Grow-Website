export const formatSemesterLabel = (raw: string): string =>
  raw.replace(/^(\d{4})-[12]\s+/, '$1 ');

/**
 * Convert a `?semester=` URL param (e.g. "2024-fall") into the display label
 * produced by formatSemesterLabel (e.g. "2024 Fall"). Used to restrict the
 * Past Projects view to a single semester when linked from a past-event page.
 * Returns null for input that isn't a `<year>-<season>` pair.
 */
export const semesterParamToLabel = (param: string): string | null => {
  const match = param.trim().match(/^(\d{4})-(fall|spring)$/i);
  if (!match) {
    return null;
  }
  const [, year, season] = match;
  const seasonName = season.toLowerCase() === 'fall' ? 'Fall' : 'Spring';
  return `${year} ${seasonName}`;
};
