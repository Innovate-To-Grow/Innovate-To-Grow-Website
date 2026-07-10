const DATE_PART_OPTIONS: Intl.DateTimeFormatOptions = {
  weekday: 'long',
  month: 'long',
  day: 'numeric',
};

const FULL_DATE_FORMATTER = new Intl.DateTimeFormat('en-US', {
  ...DATE_PART_OPTIONS,
  year: 'numeric',
});

const DATE_WITHOUT_YEAR_FORMATTER = new Intl.DateTimeFormat('en-US', DATE_PART_OPTIONS);

const parseLocalDate = (value: string): Date => {
  const datePart = value.includes('T') ? value.split('T')[0] : value;
  return new Date(`${datePart}T00:00:00`);
};

const isSameDay = (start: Date, end: Date): boolean =>
  start.getFullYear() === end.getFullYear()
  && start.getMonth() === end.getMonth()
  && start.getDate() === end.getDate();

/**
 * Formats an inclusive, all-day event date range without shifting ISO dates by timezone.
 * A missing end date is treated as a single-day event for compatibility with older APIs.
 */
export const formatEventDateRange = (startDate: string, endDate?: string | null): string => {
  const start = parseLocalDate(startDate);
  const end = parseLocalDate(endDate || startDate);

  if (isSameDay(start, end)) {
    return FULL_DATE_FORMATTER.format(start);
  }

  if (start.getFullYear() === end.getFullYear()) {
    return `${DATE_WITHOUT_YEAR_FORMATTER.format(start)} – ${FULL_DATE_FORMATTER.format(end)}`;
  }

  return `${FULL_DATE_FORMATTER.format(start)} – ${FULL_DATE_FORMATTER.format(end)}`;
};
