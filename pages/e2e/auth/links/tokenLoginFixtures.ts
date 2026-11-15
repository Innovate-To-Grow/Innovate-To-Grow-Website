import {loginResponse} from '../../helpers';

export const SUCCESS = loginResponse({user: {email: 'token-login@example.com', member_uuid: 'm-token'}});

const UNUSABLE_LINK = "This sign-in link can't be used.";
export const EXPIRED_LINK = 'This sign-in link has expired.';
export const USED_LINK = 'This sign-in link has already been used.';
export const CANT_VERIFY_LINK = "We couldn't verify your sign-in link right now.";
// The code step: the server's own (generic) acknowledgement, then a nudge for a mistyped address.
export const CODE_ACK = 'If an eligible account exists, a verification code has been sent.';
export const CODE_HINT = "Didn't get a code? Check the address above or go back to correct it.";

// The fallback is informational: none of the error markup may appear.
export const ERROR_MARKUP = '.magic-login-error, .auth-alert.error';

interface TokenCase {
  name: string;
  path: string;
  endpoint: string;
  /** Login links fall back to an emailed code; other tokens keep their error text. */
  fallback: boolean;
  invalidText: string;
  noTokenText: string;
}

export const cases: TokenCase[] = [
  {name: 'login-link', path: '/login-link', endpoint: '**/mail/login-link/', fallback: true, invalidText: UNUSABLE_LINK, noTokenText: UNUSABLE_LINK},
  // Legacy aliases from already-sent emails redirect into /login-link.
  {name: 'magic-alias', path: '/magic-login', endpoint: '**/mail/login-link/', fallback: true, invalidText: UNUSABLE_LINK, noTokenText: UNUSABLE_LINK},
  {name: 'ticket-alias', path: '/ticket-login', endpoint: '**/mail/login-link/', fallback: true, invalidText: UNUSABLE_LINK, noTokenText: UNUSABLE_LINK},
  {
    name: 'impersonate',
    path: '/impersonate-login',
    endpoint: '**/authn/impersonate-login/',
    fallback: false,
    invalidText: 'This impersonation link is invalid or has expired.',
    noTokenText: 'No impersonation token provided.',
  },
];

// /unsubscribe-login is retired: no email has produced it for months and every
// token it carried has expired. Old links land on the account page, where email
// preferences live, and the token never reaches a request.
export const RETIRED_UNSUBSCRIBE_TOKEN = 'retired-unsubscribe-7c4e1a';
