import {describe, it, expect} from 'vitest';

describe('Router', () => {
  it('router object is created without errors', async () => {
    const {router} = await import('../router');
    expect(router).toBeDefined();
    expect(router.routes).toBeDefined();
    expect(router.routes.length).toBeGreaterThan(0);
  });
});
