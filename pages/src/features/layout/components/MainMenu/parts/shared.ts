import {type MenuItem} from '@/features/layout/api';
import {safeHref} from '@/lib/security';

export const buildHref = (item: MenuItem) => safeHref(item.url);

/** Placeholder widths (px) for loading skeleton — similar footprint to real nav labels */
export const MENU_BAR_SKELETON_WIDTHS_PX = [56, 72, 64, 48, 80, 68, 52] as const;

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'] as const;
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] as const;

const pad2 = (value: number) => String(value).padStart(2, '0');

/**
 * The date shown at the right end of the menu row, as on the UC Merced theme:
 * "Sunday 18 October 2026" (the sheet sets it in capitals), plus the ISO date
 * for the <time> element. Uses the visitor's local date.
 */
export const formatMenuDate = (date: Date) => ({
  label: `${WEEKDAYS[date.getDay()]} ${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`,
  iso: `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`,
});

/** UC Merced utility links shown in the blue bar (desktop) and the mobile menu. */
export const UNIVERSITY_LINKS = [
  {label: 'Directory', href: 'https://directory.ucmerced.edu/'},
  {label: 'Apply', href: 'https://admissions.ucmerced.edu/first-year/apply?button'},
  {label: 'Give', href: 'https://giving.ucmerced.edu/'},
] as const;

export const memberDisplayName = (
  user: {email?: string | null; phone?: string | null} | null,
  formatPhone: (phone: string) => string,
) => user?.email || formatPhone(user?.phone ?? '') || 'Member';
