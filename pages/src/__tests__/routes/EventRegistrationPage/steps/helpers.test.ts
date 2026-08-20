import {describe, expect, it} from 'vitest';

import {getRegistrationErrorMessage} from '@/routes/EventRegistrationPage/steps/helpers';

const FALLBACK = 'An unexpected error occurred. Please try again.';

describe('getRegistrationErrorMessage', () => {
  it('falls back for non-object errors', () => {
    expect(getRegistrationErrorMessage(null)).toBe(FALLBACK);
    expect(getRegistrationErrorMessage(undefined)).toBe(FALLBACK);
    expect(getRegistrationErrorMessage('boom')).toBe(FALLBACK);
  });

  it('falls back when the response carries no data', () => {
    expect(getRegistrationErrorMessage({})).toBe(FALLBACK);
    expect(getRegistrationErrorMessage({response: {}})).toBe(FALLBACK);
  });

  it('prefers `detail`, then `message`', () => {
    expect(getRegistrationErrorMessage({response: {data: {detail: 'Closed.', message: 'ignored'}}})).toBe('Closed.');
    expect(getRegistrationErrorMessage({response: {data: {message: 'Closed.'}}})).toBe('Closed.');
  });

  it('skips over-long `detail` and `message` strings', () => {
    const long = 'x'.repeat(301);
    expect(getRegistrationErrorMessage({response: {data: {detail: long}}})).toBe(FALLBACK);
    expect(getRegistrationErrorMessage({response: {data: {detail: long, message: 'ok'}}})).toBe('ok');
  });

  it('reads only the FIRST field key, unlike the subscribe helper which joins all', () => {
    const err = {response: {data: {email: ['Invalid email.'], code: ['Expired.']}}};
    expect(getRegistrationErrorMessage(err)).toBe('Invalid email.');
  });

  it('accepts a bare string field value', () => {
    expect(getRegistrationErrorMessage({response: {data: {email: 'Required.'}}})).toBe('Required.');
  });

  it('falls back when the first field key is unusable', () => {
    const long = 'x'.repeat(301);
    expect(getRegistrationErrorMessage({response: {data: {email: []}}})).toBe(FALLBACK);
    expect(getRegistrationErrorMessage({response: {data: {email: [42]}}})).toBe(FALLBACK);
    expect(getRegistrationErrorMessage({response: {data: {email: [long]}}})).toBe(FALLBACK);
    expect(getRegistrationErrorMessage({response: {data: {email: long}}})).toBe(FALLBACK);
    expect(getRegistrationErrorMessage({response: {data: {email: 42}}})).toBe(FALLBACK);
  });

  it('falls back for an empty data object with no keys', () => {
    expect(getRegistrationErrorMessage({response: {data: {}}})).toBe(FALLBACK);
  });
});
