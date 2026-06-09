import {describe, expect, it} from 'vitest';

import {getAuthApiErrorMessage, USER_FACING_GENERIC_ERROR} from '@/features/auth/components/shared/apiErrors';

describe('auth API error helpers', () => {
  it('exports the generic account UI error', () => {
    expect(USER_FACING_GENERIC_ERROR).toBe('An unknown error occurred.');
  });

  it('returns safe string and array messages from response data', () => {
    expect(getAuthApiErrorMessage({response: {data: {email: ['Use a valid email.']}}})).toBe('Use a valid email.');
    expect(getAuthApiErrorMessage({response: {data: {detail: 'Code expired.'}}})).toBe('Code expired.');
  });

  it('falls back for unsafe, missing, or malformed messages', () => {
    const fallback = 'An unexpected error occurred. Please try again.';
    expect(getAuthApiErrorMessage({response: {data: {detail: '<script>alert(1)</script>'}}})).toBe(fallback);
    expect(getAuthApiErrorMessage({response: {data: {detail: [42]}}})).toBe(fallback);
    expect(getAuthApiErrorMessage({response: {data: {}}})).toBe(fallback);
    expect(getAuthApiErrorMessage(new Error('internal'))).toBe(fallback);
  });
});
