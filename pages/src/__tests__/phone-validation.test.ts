import {describe, expect, it} from 'vitest';
import {validatePhoneDigits} from '@/lib/phoneRegions';

describe('validatePhoneDigits', () => {
  it('returns null for empty input', () => {
    expect(validatePhoneDigits('')).toBeNull();
  });

  it('accepts valid US 10-digit number', () => {
    expect(validatePhoneDigits('6504683972')).toBeNull();
  });

  it('rejects US number with fewer than 10 digits', () => {
    expect(validatePhoneDigits('650468')).toBe('US phone numbers must be exactly 10 digits.');
  });

  it('rejects US number with more than 10 digits', () => {
    expect(validatePhoneDigits('65046839720')).toBe('US phone numbers must be exactly 10 digits.');
  });

  it('rejects non-digit characters', () => {
    expect(validatePhoneDigits('650-468-3972')).toBe('Phone number must contain only digits.');
  });
});
