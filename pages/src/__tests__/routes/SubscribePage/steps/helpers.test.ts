import {describe, expect, it} from 'vitest';

import {getSubscribeErrorMessage} from '@/routes/SubscribePage/steps/helpers';

const FALLBACK = 'An unexpected error occurred. Please try again.';

describe('getSubscribeErrorMessage', () => {
  it('falls back for non-object errors', () => {
    expect(getSubscribeErrorMessage(null)).toBe(FALLBACK);
    expect(getSubscribeErrorMessage(undefined)).toBe(FALLBACK);
    expect(getSubscribeErrorMessage('boom')).toBe(FALLBACK);
    expect(getSubscribeErrorMessage(new Error('boom'))).toBe(FALLBACK);
  });

  it('falls back when the response carries no data', () => {
    expect(getSubscribeErrorMessage({})).toBe(FALLBACK);
    expect(getSubscribeErrorMessage({response: {}})).toBe(FALLBACK);
    expect(getSubscribeErrorMessage({response: {data: undefined}})).toBe(FALLBACK);
  });

  it('prefers `detail` over every other key', () => {
    const err = {response: {data: {detail: 'Rate limited.', message: 'ignored', email: ['ignored']}}};
    expect(getSubscribeErrorMessage(err)).toBe('Rate limited.');
  });

  it('falls back to `message` when `detail` is absent or unusable', () => {
    expect(getSubscribeErrorMessage({response: {data: {message: 'Try later.'}}})).toBe('Try later.');
    expect(getSubscribeErrorMessage({response: {data: {detail: 42, message: 'Try later.'}}})).toBe('Try later.');
  });

  it('skips over-long `detail` and `message` strings', () => {
    const long = 'x'.repeat(301);
    expect(getSubscribeErrorMessage({response: {data: {detail: long}}})).toBe(FALLBACK);
    expect(getSubscribeErrorMessage({response: {data: {detail: long, message: long}}})).toBe(FALLBACK);
    expect(getSubscribeErrorMessage({response: {data: {detail: long, message: 'ok'}}})).toBe('ok');
  });

  it('joins every field error, unlike the first-key-only registration helper', () => {
    const err = {response: {data: {email: ['Invalid email.'], code: ['Expired.']}}};
    expect(getSubscribeErrorMessage(err)).toBe('Invalid email. Expired.');
  });

  it('collects both bare-string and array field errors', () => {
    const err = {response: {data: {email: ['Invalid email.'], name: 'Required.'}}};
    expect(getSubscribeErrorMessage(err)).toBe('Invalid email. Required.');
  });

  it('drops non-string and over-long entries inside field arrays', () => {
    const long = 'x'.repeat(301);
    const err = {response: {data: {email: [42, null, long, 'Kept.']}}};
    expect(getSubscribeErrorMessage(err)).toBe('Kept.');
  });

  it('falls back when no field yields a usable string', () => {
    expect(getSubscribeErrorMessage({response: {data: {email: [], code: 42}}})).toBe(FALLBACK);
    expect(getSubscribeErrorMessage({response: {data: {email: ['x'.repeat(301)]}}})).toBe(FALLBACK);
  });
});
