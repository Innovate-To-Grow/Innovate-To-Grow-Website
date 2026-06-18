/**
 * US-only phone input helpers — AWS SNS only delivers SMS to US numbers, so the
 * national part is always 10 digits (NANP).
 */

/**
 * Extract national digits from user input; cap to 10; drop a single leading 1 when pasted as +1…
 */
export function parsePhoneInputToNationalDigits(raw: string): string {
  let digits = raw.replace(/\D/g, '');
  if (digits.length === 11 && digits.startsWith('1')) {
    digits = digits.slice(1);
  }
  return digits.slice(0, 10);
}

/** Display string for a controlled tel input: (XXX)XXX-XXXX. */
export function formatNationalInputDisplay(nationalDigits: string): string {
  const d = nationalDigits.slice(0, 10);
  if (d.length === 0) return '';
  if (d.length <= 3) return `(${d}`;
  if (d.length <= 6) return `(${d.slice(0, 3)})${d.slice(3)}`;
  return `(${d.slice(0, 3)})${d.slice(3, 6)}-${d.slice(6)}`;
}

export function nationalInputMaxLength(): number {
  return 13;
}

export function canSubmitNationalPhone(digits: string): boolean {
  if (!digits || !/^\d+$/.test(digits)) return false;
  return digits.length === 10;
}
