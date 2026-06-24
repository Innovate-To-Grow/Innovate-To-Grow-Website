import { describe, expect, it } from 'vitest';

import { identifyLoginInput } from '../identifyLoginInput';

describe('identifyLoginInput', () => {
  it('classifies a well-formed email', () => {
    expect(identifyLoginInput('ada@example.com')).toEqual({ type: 'email', value: 'ada@example.com' });
  });

  it('classifies a multi-label-domain email', () => {
    expect(identifyLoginInput('ada@mail.example.co.uk')).toEqual({
      type: 'email',
      value: 'ada@mail.example.co.uk',
    });
  });

  it('trims surrounding whitespace from an email', () => {
    expect(identifyLoginInput('  ada@example.com  ')).toEqual({ type: 'email', value: 'ada@example.com' });
  });

  it('treats an "@" string without a dotted domain as invalid', () => {
    expect(identifyLoginInput('ada@localhost')).toEqual({ type: 'invalid' });
  });

  it('classifies plain 10-digit national numbers as phone', () => {
    expect(identifyLoginInput('2025550123')).toEqual({ type: 'phone', nationalDigits: '2025550123' });
  });

  it('strips formatting from a phone number', () => {
    expect(identifyLoginInput('(202) 555-0123')).toEqual({ type: 'phone', nationalDigits: '2025550123' });
  });

  it('drops a leading +1 country code', () => {
    expect(identifyLoginInput('+1 202 555 0123')).toEqual({ type: 'phone', nationalDigits: '2025550123' });
  });

  it('rejects a too-short phone number', () => {
    expect(identifyLoginInput('202555012')).toEqual({ type: 'invalid' });
  });

  it('rejects an empty / whitespace value', () => {
    expect(identifyLoginInput('')).toEqual({ type: 'invalid' });
    expect(identifyLoginInput('   ')).toEqual({ type: 'invalid' });
  });

  it('treats a letters-without-@ value as an incomplete email, not a phone', () => {
    expect(identifyLoginInput('ada')).toEqual({ type: 'invalid' });
    expect(identifyLoginInput('1-800-FLOWERS')).toEqual({ type: 'invalid' });
  });
});
