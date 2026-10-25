// Column colours of the presentation grids, as on the reference schedule page
// (innovatetogrow.ucmerced.edu/schedule): every class keeps one colour family across its
// track columns (gold for the Engineering Capstone, teal for Civil & Environmental and
// Service Learning, navy for Software Engineering) and each further column takes the next,
// lighter step. The colours live in scheduleTones.css as
// .schedule-tone--<family>.schedule-tone--col-<n>; unknown classes fall back to gold.
import './scheduleTones.css';

const SECTION_TONE_FAMILY: Record<string, string> = {
  CAP: 'gold',
  CEE: 'teal',
  ENGSL: 'teal',
  CSE: 'navy',
};

const TONE_COLUMN_COUNT = 5;

export function scheduleToneClass(sectionCode: string, columnIndex: number): string {
  const family = SECTION_TONE_FAMILY[sectionCode.toUpperCase()] ?? 'gold';
  const column = Math.min(Math.max(columnIndex, 0), TONE_COLUMN_COUNT - 1);
  return `schedule-tone schedule-tone--${family} schedule-tone--col-${column}`;
}
