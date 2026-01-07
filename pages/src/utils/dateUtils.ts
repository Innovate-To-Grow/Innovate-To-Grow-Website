/**
 * Utility functions for date formatting.
 * 
 * These functions parse date strings as local dates to avoid timezone issues
 * when converting ISO date strings (YYYY-MM-DD) to Date objects.
 */

/**
 * Parses an ISO date string (YYYY-MM-DD) as a local date.
 * This prevents timezone shifts that occur when using new Date() directly.
 * 
 * @param dateString - ISO date string in format "YYYY-MM-DD"
 * @returns Date object representing the date in local timezone
 */
export const parseLocalDate = (dateString: string): Date => {
  const [year, month, day] = dateString.split('-').map(Number);
  return new Date(year, month - 1, day); // month is 0-indexed in Date constructor
};

/**
 * Formats an event date string to a human-readable format.
 * 
 * @param dateString - ISO date string in format "YYYY-MM-DD"
 * @param options - Optional Intl.DateTimeFormatOptions for customization
 * @returns Formatted date string
 */
export const formatEventDate = (
  dateString: string,
  options: Intl.DateTimeFormatOptions = {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }
): string => {
  const date = parseLocalDate(dateString);
  return date.toLocaleDateString('en-US', options);
};

/**
 * Formats a date string to a shorter format (without weekday).
 * Useful for lists and compact displays.
 * 
 * @param dateString - ISO date string in format "YYYY-MM-DD"
 * @returns Formatted date string (e.g., "January 15, 2024")
 */
export const formatEventDateShort = (dateString: string): string => {
  return formatEventDate(dateString, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
};


