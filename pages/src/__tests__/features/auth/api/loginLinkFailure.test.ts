import {AxiosError, type AxiosResponse} from 'axios';
import {describe, expect, it} from 'vitest';

import {
  MalformedLoginResponseError,
  SessionNotSavedError,
} from '@/features/auth/api/errors';
import {classifyLoginLinkFailure} from '@/features/auth/api/loginLinkFailure';

const httpError = (status: number, data?: unknown) =>
  new AxiosError(
    `Request failed with status code ${status}`,
    status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
    undefined,
    undefined,
    {status, statusText: '', headers: {}, config: {}, data} as AxiosResponse,
  );

const kindOf = (error: unknown) => classifyLoginLinkFailure(error).kind;

describe('classifyLoginLinkFailure', () => {
  describe('the machine-readable code', () => {
    it.each([
      ['already_used', 'already_used'],
      ['expired', 'expired'],
      ['invalid_link', 'invalid'],
      ['token_required', 'invalid'],
      ['a code this frontend has never heard of', 'invalid'],
    ])('maps code %s to %s', (code, kind) => {
      const body = {detail: 'Whatever the backend says.', code};
      expect(kindOf(httpError(400, body))).toBe(kind);
    });

    it.each([
      ['expired', {code: 'invalid_link', detail: 'Invalid or expired login link.'}, 'invalid'],
      ['used', {code: 'invalid_link', detail: 'This login link has already been used.'}, 'invalid'],
      ['invalid', {code: 'expired', detail: 'Invalid login link.'}, 'expired'],
      ['used', {code: 'expired', detail: 'This login link has already been used.'}, 'expired'],
      ['expired', {code: 'already_used', detail: 'This login link has expired.'}, 'already_used'],
      ['an unknown code', {code: 'nope', detail: 'This login link has expired.'}, 'invalid'],
      ['an empty code', {code: '', detail: 'This login link has expired.'}, 'invalid'],
    ])('lets a string code win over a conflicting detail (%s)', (_label, body, kind) => {
      expect(kindOf(httpError(400, body))).toBe(kind);
    });

    it.each([
      ['a numeric code', {code: 7, detail: 'This login link has expired.'}, 'expired'],
      ['a null code', {code: null, detail: 'This login link has already been used.'}, 'already_used'],
      ['an object code', {code: {}, detail: 'This login link has expired.'}, 'expired'],
    ])('reads the detail when the code is not a string (%s)', (_label, body, kind) => {
      expect(kindOf(httpError(400, body))).toBe(kind);
    });
  });

  describe('the detail text of an older backend (no code)', () => {
    it.each([
      ['This login link has already been used.', 'already_used'],
      ['this LOGIN link has ALREADY BEEN USED', 'already_used'],
      ['This login link has expired.', 'expired'],
      ['Invalid login link.', 'invalid'],
      ['Token is required.', 'invalid'],
      ['', 'invalid'],
    ])('reads %j as %s', (detail, kind) => {
      expect(kindOf(httpError(400, {detail}))).toBe(kind);
    });

    it.each([
      ['no body', undefined],
      ['a non-JSON body', '<html>Bad Request</html>'],
      ['a null body', null],
      ['an array body', ['expired']],
      ['a non-string detail', {detail: {expired: true}}],
    ])('treats %s as invalid', (_label, body) => {
      expect(kindOf(httpError(400, body))).toBe('invalid');
    });
  });

  describe('the HTTP status', () => {
    it('is rate limited on 429, and that is retryable', () => {
      expect(classifyLoginLinkFailure(httpError(429, {detail: 'Throttled.'}))).toEqual({
        kind: 'rate_limited',
        retryable: true,
        redirectTo: null,
      });
    });

    it.each<[string, unknown]>([
      ['plain text', 'Too Many Requests'],
      ['an HTML page', '<html><body>Blocked</body></html>'],
      ['no body', undefined],
      ['an unrelated JSON body', {code: 'expired', detail: 'This login link has expired.'}],
    ])('is rate limited on a 429 from an edge or WAF with %s', (_label, body) => {
      // Only a proxy or WAF can answer 429 here now; whatever it says, the link
      // itself was not judged, so it is retryable and never read as used or expired.
      expect(classifyLoginLinkFailure(httpError(429, body))).toEqual({
        kind: 'rate_limited',
        retryable: true,
        redirectTo: null,
      });
    });

    it.each([408, 500, 502, 503, 504])('is unavailable and retryable on %i', (status) => {
      expect(classifyLoginLinkFailure(httpError(status))).toEqual({
        kind: 'unavailable',
        retryable: true,
        redirectTo: null,
      });
    });

    it('is unavailable and retryable when there is no response at all', () => {
      expect(classifyLoginLinkFailure(new AxiosError('Network Error', AxiosError.ERR_NETWORK))).toEqual({
        kind: 'unavailable',
        retryable: true,
        redirectTo: null,
      });
    });

    it.each([401, 403, 404, 410, 422])('is terminal on %i, even when the body claims a reason', (status) => {
      expect(
        classifyLoginLinkFailure(
          httpError(status, {
            code: 'already_used',
            detail: 'This login link has already been used.',
            redirect_to: '/schedule',
          }),
        ),
      ).toEqual({kind: 'invalid', retryable: false, redirectTo: null});
    });

    it.each([
      ['already_used', {code: 'already_used'}],
      ['expired', {code: 'expired'}],
      ['invalid', {code: 'invalid_link'}],
    ])('marks a 400 %s as not retryable', (_kind, body) => {
      expect(classifyLoginLinkFailure(httpError(400, body)).retryable).toBe(false);
    });
  });

  describe('errors that are not an HTTP answer', () => {
    it('is the only place a browser that could not store the session is reported', () => {
      expect(classifyLoginLinkFailure(new SessionNotSavedError())).toEqual({
        kind: 'session_not_saved',
        retryable: false,
        redirectTo: null,
      });
    });

    it('does not mistake a plain Error with the storage message for the typed error', () => {
      expect(kindOf(new Error('Unable to persist the authentication session.'))).toBe('unavailable');
    });

    it.each([
      ['a malformed 2xx body', new MalformedLoginResponseError()],
      ['a TypeError', new TypeError('Cannot read properties of undefined')],
      ['a thrown string', 'boom'],
      ['undefined', undefined],
      ['null', null],
    ])('treats %s as unavailable and retryable', (_label, error) => {
      expect(classifyLoginLinkFailure(error)).toEqual({
        kind: 'unavailable',
        retryable: true,
        redirectTo: null,
      });
    });
  });

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
