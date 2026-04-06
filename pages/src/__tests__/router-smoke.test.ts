import {describe, it, expect} from 'vitest';

describe('Router', () => {
  it('router object is created without errors', async () => {
    const {router} = await import('../router');
    expect(router).toBeDefined();
    expect(router.routes).toBeDefined();
    expect(router.routes.length).toBeGreaterThan(0);
  });

  it('keeps acknowledgement on a dedicated route instead of CMSPageComponent', async () => {
    const {router} = await import('../router');
    const {CMSPageComponent} = await import('../components/CMS');
    const rootRoute = router.routes.find((route) => route.path === '/');
    const acknowledgementRoute = rootRoute?.children?.find((route) => route.path === 'acknowledgement');

    expect(acknowledgementRoute).toBeDefined();
    expect(acknowledgementRoute?.element?.type).not.toBe(CMSPageComponent);
  });
});
