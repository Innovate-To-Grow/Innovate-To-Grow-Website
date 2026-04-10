import {describe, expect, it} from 'vitest';
import {validatePhoneDigits} from '../constants/phoneRegions';

describe('validatePhoneDigits', () => {
  it('returns null for empty input', () => {
    expect(validatePhoneDigits('', '1-US')).toBeNull();
  });

  it('accepts valid US 10-digit number', () => {
    expect(validatePhoneDigits('6504683972', '1-US')).toBeNull();
  });

  it('rejects US number with fewer than 10 digits', () => {
    expect(validatePhoneDigits('650468', '1-US')).toBe('US/Canada phone numbers must be exactly 10 digits.');
  });

  it('rejects US number with more than 10 digits', () => {
    expect(validatePhoneDigits('65046839720', '1-US')).toBe('US/Canada phone numbers must be exactly 10 digits.');
  });

  it('accepts valid Canada 10-digit number', () => {
    expect(validatePhoneDigits('4161234567', '1-CA')).toBeNull();
  });

  it('accepts valid China 11-digit number', () => {
    expect(validatePhoneDigits('13812345678', '86')).toBeNull();
  });

  it('rejects China number with 10 digits', () => {
    expect(validatePhoneDigits('1381234567', '86')).toBe('China phone numbers must be exactly 11 digits.');
  });

  it('accepts generic region with 7 digits', () => {
    expect(validatePhoneDigits('1234567', '44')).toBeNull();
  });

  it('rejects generic region with 3 digits', () => {
    expect(validatePhoneDigits('123', '44')).toBe('Phone number is too short (minimum 4 digits).');
  });

  it('rejects generic region with 16 digits', () => {
    expect(validatePhoneDigits('1234567890123456', '44')).toBe('Phone number is too long (maximum 15 digits).');
  });

  it('rejects non-digit characters', () => {
    expect(validatePhoneDigits('650-468-3972', '1-US')).toBe('Phone number must contain only digits.');
  });
});
