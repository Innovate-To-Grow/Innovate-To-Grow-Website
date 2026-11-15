import {beforeEach, describe, expect, it, vi} from 'vitest';

const authApiPost = vi.fn();
const authApiGet = vi.fn();
const persistAuthSession = vi.fn();

vi.mock('@/features/auth/api/client', () => ({
  authApi: {get: authApiGet, post: authApiPost},
  isDefinitiveAuthFailure: vi.fn(() => false),
}));

vi.mock('@/features/auth/api/storage', () => ({
  clearTokens: vi.fn(),
  getAccessToken: vi.fn(() => null),
  getStoredSession: vi.fn(() => null),
  persistAuthSession,
  updateStoredSessionProfile: vi.fn(),
}));

const LOGIN = {
  access: 'access-token',
  refresh: 'refresh-token',
  user: {member_uuid: 'member-a', email: '', phone: '+12095550101', is_staff: false},
  next_step: 'account',
  redirect_to: '/subscribe',
  kind: 'sign_in',
};

describe('SMS short links and the /register destination', () => {
  beforeEach(() => {
    vi.resetModules();
    authApiPost.mockReset();
    authApiGet.mockReset();
    persistAuthSession.mockReset();
  });

  it('opens a personal link: stores the session it signs in', async () => {
    authApiPost.mockResolvedValue({data: LOGIN});
    const {openSmsLink} = await import('@/features/auth/api/session');

    const result = await openSmsLink('AbCdEfGhIjKlMnOpQrStUv');

    expect(authApiPost).toHaveBeenCalledWith('/mail/sms-link/', {token: 'AbCdEfGhIjKlMnOpQrStUv'}, {skipAuth: true});
    expect(result).toEqual({kind: 'sign_in', login: LOGIN});
    expect(persistAuthSession).toHaveBeenCalledWith(LOGIN);
  });

  it('opens a shared link: only says where to go', async () => {
    authApiPost.mockResolvedValue({data: {kind: 'redirect', redirect_to: '/event-registration?event=x'}});
    const {openSmsLink} = await import('@/features/auth/api/session');

    await expect(openSmsLink('token-token-token-tok')).resolves.toEqual({
      kind: 'redirect',
      redirectTo: '/event-registration?event=x',
    });
    expect(persistAuthSession).not.toHaveBeenCalled();
  });

  it('treats a redirect without a destination, and a 2xx that is no login, carefully', async () => {
    const {openSmsLink} = await import('@/features/auth/api/session');
    const {MalformedLoginResponseError} = await import('@/features/auth/api/errors');

    authApiPost.mockResolvedValueOnce({data: {kind: 'redirect', redirect_to: 42}});
    await expect(openSmsLink('t')).resolves.toEqual({kind: 'redirect', redirectTo: null});
    authApiPost.mockResolvedValueOnce({data: '<html>captive portal</html>'});
    await expect(openSmsLink('t')).rejects.toBeInstanceOf(MalformedLoginResponseError);
    expect(persistAuthSession).not.toHaveBeenCalled();
  });

  it('reads where /register leads', async () => {
    const {getRegisterLinkPath} = await import('@/features/auth/api/session');

    authApiGet.mockResolvedValueOnce({data: {path: '/event-registration?event=fall'}});
    await expect(getRegisterLinkPath()).resolves.toBe('/event-registration?event=fall');
    expect(authApiGet).toHaveBeenCalledWith('/mail/register-link/', {skipAuth: true});
    authApiGet.mockResolvedValueOnce({data: {path: null}});
    await expect(getRegisterLinkPath()).resolves.toBeNull();
  });
});
