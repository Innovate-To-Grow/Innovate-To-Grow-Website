/**
 * The server accepted a sign-in, but the browser would not store the session
 * (storage blocked, full, or unavailable). The one-time credential behind the
 * sign-in has already been spent, so callers must not offer a retry.
 */
export class SessionNotSavedError extends Error {
  constructor(message = 'Unable to persist the authentication session.') {
    super(message);
    this.name = 'SessionNotSavedError';
  }
}

/**
 * A 2xx answer that is not a login response, e.g. a proxy, captive portal, or
 * SPA rewrite answering with HTML. The credential was most likely never
 * consumed, so it is a transient failure and not a browser problem.
 */
export class MalformedLoginResponseError extends Error {
  constructor(message = 'The server sent an unexpected sign-in response.') {
    super(message);
    this.name = 'MalformedLoginResponseError';
  }
}
