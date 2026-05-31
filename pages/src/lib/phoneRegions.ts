/**
 * Phone region/country code choices.
 * Mirrors src/authn/models/contact/phone_regions.py — single source for the frontend.
 */
export const PHONE_REGION_CHOICES: ReadonlyArray<{ code: string; label: string }> = [
  // North America
  { code: '1-US', label: 'United States' },
  { code: '1-CA', label: 'Canada' },
  { code: '52', label: 'Mexico' },
  // Greater China
  { code: '86', label: 'China P.R.C.' },
  { code: '852', label: 'Hong Kong S.A.R.' },
  { code: '853', label: 'Macau S.A.R.' },
  { code: '886', label: 'Taiwan R.O.C.' },
  // East Asia
  { code: '81', label: 'Japan' },
  { code: '82', label: 'South Korea' },
  // Southeast Asia
  { code: '60', label: 'Malaysia' },
  { code: '62', label: 'Indonesia' },
  { code: '63', label: 'Philippines' },
  { code: '65', label: 'Singapore' },
  { code: '66', label: 'Thailand' },
  { code: '84', label: 'Vietnam' },
  // South Asia
  { code: '91', label: 'India' },
  { code: '92', label: 'Pakistan' },
  { code: '94', label: 'Sri Lanka' },
  { code: '880', label: 'Bangladesh' },
  // Europe
  { code: '44', label: 'United Kingdom' },
  { code: '33', label: 'France' },
  { code: '49', label: 'Germany' },
  { code: '39', label: 'Italy' },
  { code: '34', label: 'Spain' },
  { code: '31', label: 'Netherlands' },
  { code: '46', label: 'Sweden' },
  { code: '47', label: 'Norway' },
  { code: '45', label: 'Denmark' },
  { code: '41', label: 'Switzerland' },
  { code: '43', label: 'Austria' },
  { code: '32', label: 'Belgium' },
  { code: '48', label: 'Poland' },
  { code: '420', label: 'Czech Republic' },
  // Middle East
  { code: '972', label: 'Israel' },
  { code: '971', label: 'United Arab Emirates' },
  { code: '966', label: 'Saudi Arabia' },
  { code: '974', label: 'Qatar' },
  { code: '965', label: 'Kuwait' },
  { code: '968', label: 'Oman' },
  { code: '90', label: 'Turkey' },
  // Oceania
  { code: '61', label: 'Australia' },
  { code: '64', label: 'New Zealand' },
  // South America
  { code: '55', label: 'Brazil' },
  { code: '54', label: 'Argentina' },
  { code: '56', label: 'Chile' },
  { code: '57', label: 'Colombia' },
  { code: '51', label: 'Peru' },
  // Africa
  { code: '27', label: 'South Africa' },
  { code: '20', label: 'Egypt' },
  { code: '234', label: 'Nigeria' },
  { code: '254', label: 'Kenya' },
];

/** Maximum national-digit length for a given country code. */
export function maxPhoneDigits(regionCode: string): number {
  const cc = regionCode.split('-')[0];
  if (cc === '1') return 10;
  if (cc === '86') return 11;
  return 15;
}

/**
 * Validate a national phone number (digits only, no country-code prefix).
 * Returns an error message string if invalid, or `null` if valid.
 */
export function validatePhoneDigits(digits: string, regionCode: string): string | null {
  if (!digits) return null; // empty is not an error here; "required" is handled separately

  if (!/^\d+$/.test(digits)) return 'Phone number must contain only digits.';

  const cc = regionCode.split('-')[0];
  const max = maxPhoneDigits(regionCode);

  if (cc === '1') {
    if (digits.length !== max) return 'US/Canada phone numbers must be exactly 10 digits.';
    return null;
  }
  if (cc === '86') {
    if (digits.length !== max) return 'China phone numbers must be exactly 11 digits.';
    return null;
  }

  if (digits.length < 4) return 'Phone number is too short (minimum 4 digits).';
  if (digits.length > max) return 'Phone number is too long (maximum 15 digits).';
  return null;
}

/**
 * Format raw national digits for display.
 * US/Canada: (206)333-8881
 * China: 131 2345 6789
 * Others: digits as-is
 */
export function formatPhoneDisplay(digits: string, regionCode: string): string {
  if (!digits) return '';
  const cc = regionCode.split('-')[0];

  if (cc === '1') {
    const area = digits.slice(0, 3);
    const mid = digits.slice(3, 6);
    const last = digits.slice(6, 10);
    if (digits.length <= 3) return `(${area}`;
    if (digits.length <= 6) return `(${area})${mid}`;
    return `(${area})${mid}-${last}`;
  }

  if (cc === '86') {
    const p1 = digits.slice(0, 3);
    const p2 = digits.slice(3, 7);
    const p3 = digits.slice(7, 11);
    if (digits.length <= 3) return p1;
    if (digits.length <= 7) return `${p1} ${p2}`;
    return `${p1} ${p2} ${p3}`;
  }

  return digits;
}

/** Strip formatting characters, returning only digits. */
export function stripPhoneFormat(value: string): string {
  return value.replace(/\D/g, '');
}
