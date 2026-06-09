import {describe, expect, it} from 'vitest';

import {EMBED_APP_ROUTE_COMPONENTS, resolveEmbedAppRoute} from '@/features/cms/components/embedAppRoutes';

describe('embedAppRoutes', () => {
  it('resolves known CMS embed app routes and rejects empty or unknown routes', () => {
    expect(resolveEmbedAppRoute('/schedule')).toBe(EMBED_APP_ROUTE_COMPONENTS['/schedule']);
    expect(resolveEmbedAppRoute('/subscribe')).toBe(EMBED_APP_ROUTE_COMPONENTS['/subscribe']);
    expect(resolveEmbedAppRoute(undefined)).toBeNull();
    expect(resolveEmbedAppRoute(null)).toBeNull();
    expect(resolveEmbedAppRoute('/missing')).toBeNull();
  });
});
