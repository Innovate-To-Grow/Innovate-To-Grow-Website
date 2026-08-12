/**
 * Phone region/country code choices.
 * Mirrors src/authn/models/contact/phone_regions.py — single source for the frontend.
 *
 * US-only: AWS SNS in this account only delivers SMS to US numbers, so the United
 * States is the only supported region. The `regionCode` parameters below are kept
 * for call-site compatibility but always resolve to the US (+1) rules.
 */
export const PHONE_REGION_CHOICES: ReadonlyArray<{ code: string; label: string }> = [
  { code: '1-US', label: 'United States' },
];

/** Maximum national-digit length. US numbers are always 10 digits. */
export function maxPhoneDigits(): number {
  return 10;
}

/**
 * Validate a national phone number (digits only, no country-code prefix).
 * Returns an error message string if invalid, or `null` if valid.
 */
export function validatePhoneDigits(digits: string): string | null {
  if (!digits) return null; // empty is not an error here; "required" is handled separately

  if (!/^\d+$/.test(digits)) return 'Phone number must contain only digits.';

  if (digits.length !== 10) return 'US phone numbers must be exactly 10 digits.';
  return null;
}

/**
 * Format raw national digits for display.
 * US: (206)333-8881
 */
export function formatPhoneDisplay(digits: string): string {
  if (!digits) return '';

  const area = digits.slice(0, 3);
  const mid = digits.slice(3, 6);
  const last = digits.slice(6, 10);
  if (digits.length <= 3) return `(${area}`;
  if (digits.length <= 6) return `(${area})${mid}`;
  return `(${area})${mid}-${last}`;
}

/** Strip formatting characters, returning only digits. */
export function stripPhoneFormat(value: string): string {
  return value.replace(/\D/g, '');
}
