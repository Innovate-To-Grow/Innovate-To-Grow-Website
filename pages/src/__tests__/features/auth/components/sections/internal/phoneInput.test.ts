import {describe, expect, it} from 'vitest';

import {
  canSubmitNationalPhone,
  capNationalDigitsForRegion,
  formatNationalInputDisplay,
  getNationalDigitCap,
  nationalInputMaxLength,
  parsePhoneInputToNationalDigits,
} from '@/features/auth/components/sections/internal/phoneInput';
import {formatPhoneDisplay, getDialCode} from '@/features/auth/components/sections/internal/helpers';

describe('phone input helpers', () => {
  it('derives digit caps and max display lengths by region', () => {
    expect(getNationalDigitCap('1-US')).toBe(10);
    expect(getNationalDigitCap('86')).toBe(11);
    expect(getNationalDigitCap('852')).toBe(8);
    expect(getNationalDigitCap('886')).toBe(9);
    expect(getNationalDigitCap('unknown')).toBe(15);
    expect(nationalInputMaxLength('1-US')).toBe(13);
    expect(nationalInputMaxLength('86')).toBe(13);
  });

  it('parses and formats NANP national phone input', () => {
    expect(parsePhoneInputToNationalDigits('+1 (209) 555-1212', '1-US')).toBe('2095551212');
    expect(parsePhoneInputToNationalDigits('209555121234', '1-US')).toBe('2095551212');
    expect(formatNationalInputDisplay('1-US', '')).toBe('');
    expect(formatNationalInputDisplay('1-US', '209')).toBe('(209');
    expect(formatNationalInputDisplay('1-US', '209555')).toBe('(209)555');
    expect(formatNationalInputDisplay('1-US', '2095551212')).toBe('(209)555-1212');
  });

  it('formats international national input in compact groups', () => {
    expect(formatNationalInputDisplay('86', '')).toBe('');
    expect(formatNationalInputDisplay('86', '13800138000')).toBe('1380 0138 000');
    expect(capNationalDigitsForRegion('12345678901234567890', '852')).toBe('12345678');
  });

  it('validates submit-ready digit strings', () => {
    expect(canSubmitNationalPhone('', '1-US')).toBe(false);
    expect(canSubmitNationalPhone('abc', '1-US')).toBe(false);
    expect(canSubmitNationalPhone('2095551212', '1-US')).toBe(true);
    expect(canSubmitNationalPhone('123456', '86')).toBe(false);
    expect(canSubmitNationalPhone('1234567', '86')).toBe(true);
    expect(canSubmitNationalPhone('1234567890123456', '86')).toBe(false);
  });

  it('formats stored phone numbers for display across supported regions', () => {
    expect(getDialCode('1-US')).toBe('+1');
    expect(formatPhoneDisplay('+12095551212', '1-US')).toBe('(209)555-1212');
    expect(formatPhoneDisplay('5551212', '1-US')).toBe('555-1212');
    expect(formatPhoneDisplay('+8613800138000', '86')).toBe('138 0013 8000');
    expect(formatPhoneDisplay('+85212345678', '852')).toBe('1234 5678');
    expect(formatPhoneDisplay('+886912345678', '886')).toBe('9 1234 5678');
    expect(formatPhoneDisplay('+819012345678', '81')).toBe('90 1234 5678');
    expect(formatPhoneDisplay('+441234567890', '44')).toBe('1234 567890');
    expect(formatPhoneDisplay('+919876543210', '91')).toBe('98765 43210');
    expect(formatPhoneDisplay('+33612345678', '33')).toBe('6 12 34 56 78');
    expect(formatPhoneDisplay('1234567890123', '999')).toBe('1234 5678 9012 3');
  });
});
