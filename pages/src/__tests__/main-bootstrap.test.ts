import {describe, expect, it, vi} from 'vitest';

const captureAuthCallbackParams = vi.hoisted(() => vi.fn());
const mountApp = vi.hoisted(() => vi.fn());
const markIsolatedIframeRoute = vi.hoisted(() => vi.fn());
const loadThirdPartyScripts = vi.hoisted(() => vi.fn());

vi.mock('@/features/auth/api/callbackParams', () => ({captureAuthCallbackParams}));
vi.mock('@/app/providers', () => ({mountApp}));
vi.mock('@/app/thirdPartyLoaders', () => ({
  markIsolatedIframeRoute,
  loadThirdPartyScripts,
}));

describe('application bootstrap ordering', () => {
  it('captures callback parameters before mounting and creating the router', async () => {
    await import('@/main');

    expect(captureAuthCallbackParams).toHaveBeenCalledOnce();
    expect(mountApp).toHaveBeenCalledOnce();
    expect(captureAuthCallbackParams.mock.invocationCallOrder[0])
      .toBeLessThan(mountApp.mock.invocationCallOrder[0]);
  });
});
