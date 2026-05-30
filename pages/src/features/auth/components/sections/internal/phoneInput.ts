/** US / Canada — national part is always 10 digits. */
const NANP_REGIONS = new Set(['1-US', '1-CA']);

export function getNationalDigitCap(region: string): number {
  if (NANP_REGIONS.has(region)) return 10;
  if (region === '86') return 11;
  if (region === '852' || region === '853') return 8;
  if (region === '886') return 9;
  if (region === '81' || region === '82') return 11;
  if (region === '44' || region === '91' || region === '52') return 10;
  if (region === '61') return 9;
  if (region === '49') return 11;
  if (region === '33') return 9;
  if (region === '55') return 11;
  return 15;
}

/**
 * Extract national digits from user input; cap length; for NANP drop a single leading 1 when pasted as +1…
 */
export function parsePhoneInputToNationalDigits(raw: string, region: string): string {
  let digits = raw.replace(/\D/g, '');
  if (NANP_REGIONS.has(region) && digits.length === 11 && digits.startsWith('1')) {
    digits = digits.slice(1);
  }
  const cap = getNationalDigitCap(region);
  return digits.slice(0, cap);
}

/** Display string for a controlled tel input (national digits only; region selects country in a separate control). */
export function formatNationalInputDisplay(region: string, nationalDigits: string): string {
  if (NANP_REGIONS.has(region)) {
    const d = nationalDigits.slice(0, 10);
    if (d.length === 0) return '';
    if (d.length <= 3) return `(${d}`;
    if (d.length <= 6) return `(${d.slice(0, 3)})${d.slice(3)}`;
    return `(${d.slice(0, 3)})${d.slice(3, 6)}-${d.slice(6)}`;
  }
  const d = nationalDigits;
  if (d.length === 0) return '';
  return d.replace(/(\d{4})(?=\d)/g, '$1 ').trim();
}

export function capNationalDigitsForRegion(nationalDigits: string, region: string): string {
  return nationalDigits.slice(0, getNationalDigitCap(region));
}

export function nationalInputMaxLength(region: string): number {
  if (NANP_REGIONS.has(region)) return 13;
  const cap = getNationalDigitCap(region);
  return cap + Math.floor((cap - 1) / 4);
}

export function canSubmitNationalPhone(digits: string, region: string): boolean {
  if (!digits || !/^\d+$/.test(digits)) return false;
  if (NANP_REGIONS.has(region)) return digits.length === 10;
  return digits.length >= 7 && digits.length <= getNationalDigitCap(region);
}
