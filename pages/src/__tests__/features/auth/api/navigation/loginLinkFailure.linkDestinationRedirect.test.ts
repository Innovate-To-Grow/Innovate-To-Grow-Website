import {AxiosError, type AxiosResponse} from 'axios';
import {describe, expect, it} from 'vitest';
import {classifyLoginLinkFailure} from '@/features/auth/api/navigation/loginLinkFailure';

const httpError = (status: number, data?: unknown) =>
  new AxiosError(
    `Request failed with status code ${status}`,
    status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
    undefined,
    undefined,
    {status, statusText: '', headers: {}, config: {}, data} as AxiosResponse,
  );

describe('classifyLoginLinkFailure', () => {
  describe('the link destination (redirect_to)', () => {
    it.each([
      ['expired', 'expired'],
      ['already_used', 'already_used'],
    ])('is passed on with a %s link', (code, kind) => {
      expect(
        classifyLoginLinkFailure(httpError(400, {detail: 'x', code, redirect_to: '/schedule'})),
      ).toEqual({kind, retryable: false, redirectTo: '/schedule'});
    });

    it('is passed on when an older backend is read by its detail text', () => {
      expect(
        classifyLoginLinkFailure(
          httpError(400, {detail: 'This login link has expired.', redirect_to: '/event-registration?event=spring'}),
        ).redirectTo,
      ).toBe('/event-registration?event=spring');
    });

    it.each([
      ['absent', {code: 'expired'}],
      ['an empty string', {code: 'expired', redirect_to: ''}],
      ['an absolute URL', {code: 'expired', redirect_to: 'https://evil.example/x'}],
      ['a protocol-relative URL', {code: 'expired', redirect_to: '//evil.example'}],
      ['a backslash path', {code: 'expired', redirect_to: '/\\evil.example'}],
      ['a javascript: URL', {code: 'expired', redirect_to: 'javascript:alert(1)'}],
      ['a path with a control character', {code: 'expired', redirect_to: '/a\nb'}],
      ['an encoded slash', {code: 'expired', redirect_to: '/%2f%2fevil.example'}],
      ['a number', {code: 'expired', redirect_to: 7}],
      ['an object', {code: 'expired', redirect_to: {path: '/x'}}],
      ['null', {code: 'expired', redirect_to: null}],
    ])('is null when it is %s', (_label, body) => {
      expect(classifyLoginLinkFailure(httpError(400, body)).redirectTo).toBeNull();
    });

    it.each([
      ['invalid_link', {code: 'invalid_link', detail: 'Invalid login link.', redirect_to: '/schedule'}],
      ['token_required', {code: 'token_required', detail: 'Token is required.', redirect_to: '/schedule'}],
      ['an unknown code', {code: 'nope', redirect_to: '/schedule'}],
      ['a body with no reason', {redirect_to: '/schedule'}],
    ])('is never read from a %s answer', (_label, body) => {
      expect(classifyLoginLinkFailure(httpError(400, body))).toEqual({
        kind: 'invalid',
        retryable: false,
        redirectTo: null,
      });
    });

    it('is never read from a retryable failure', () => {
      expect(classifyLoginLinkFailure(httpError(429, {redirect_to: '/schedule'})).redirectTo).toBeNull();
      expect(classifyLoginLinkFailure(httpError(503, {redirect_to: '/schedule'})).redirectTo).toBeNull();
    });
  });
});
