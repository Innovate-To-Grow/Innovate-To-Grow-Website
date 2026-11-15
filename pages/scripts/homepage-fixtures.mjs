const layoutFixture = {
  menus: [
    {
      id: 'performance-main-menu',
      name: 'Main menu',
      display_name: 'Main menu',
      description: 'Synthetic local navigation fixture',
      items: [
        {type: 'home', title: 'Home', url: '/', open_in_new_tab: false, children: []},
        {type: 'app', title: 'Projects', url: '/projects', open_in_new_tab: false, children: []},
      ],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ],
  footer: {
    id: 'performance-footer',
    name: 'Performance footer',
    slug: 'performance-footer',
    content: {
      columns: [{title: 'Innovate to Grow', body_html: '<p>UC Merced School of Engineering</p>'}],
      copyright: 'Innovate to Grow',
    },
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  homepage_route: '/',
};

const homepageFixture = {
  slug: 'home',
  route: '/',
  title: 'Home',
  page_css_class: 'cms-page performance-homepage',
  page_css: '',
  meta_description: 'Synthetic local homepage used for repeatable performance measurement.',
  blocks: [
    {
      block_type: 'rich_text',
      sort_order: 0,
      data: {
        heading: 'Innovate to Grow',
        heading_level: 1,
        body_html: [
          '<div id="performance-homepage-marker">',
          '<p>Connecting UC Merced students with industry and community partners.</p>',
          '<iframe src="https://www.youtube-nocookie.com/embed/performance-fixture" title="Program overview"></iframe>',
          '</div>',
        ].join(''),
      },
    },
    {
      block_type: 'navigation_grid',
      sort_order: 1,
      data: {
        heading: 'Explore Innovate to Grow',
        items: [
          {title: 'Projects', description: 'Discover student projects.', url: '/projects'},
          {title: 'Events', description: 'Find upcoming showcase events.', url: '/events'},
        ],
      },
    },
  ],
};

function fixtureFor(pathname) {
  if (pathname === '/api/layout/') return layoutFixture;
  if (pathname === '/api/cms/homepage/') return homepageFixture;
  // Older preview builds may still resolve the homepage through the generic
  // CMS route; keep the fixture deterministic across either application build.
  if (pathname === '/api/cms/pages/') return homepageFixture;
  if (pathname === '/api/cms/embed-hosts/') {
    return {hosts: ['www.youtube-nocookie.com'], revision: 'performance-fixture'};
  }
  if (pathname === '/api/health/') {
    return {status: 'ok', database: 'ok', maintenance: false, maintenance_message: ''};
  }
  if (pathname === '/api/assistant/config/') {
    return {
      enabled: false,
      welcome_message: '',
      starter_questions: [],
      unavailable_message: 'Assistant disabled during synthetic performance measurement.',
      max_message_chars: 2000,
    };
  }
  return null;
}

export async function installSyntheticRoutes(page, targetOrigin) {
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin === targetOrigin && url.pathname === '/api/analytics/pageview/') {
      await route.fulfill({status: 204});
      return;
    }
    if (url.origin === targetOrigin && url.pathname === '/api/layout/styles.css') {
      await route.fulfill({status: 200, contentType: 'text/css', body: ':root {}'});
      return;
    }
    if (url.origin === targetOrigin && url.pathname.startsWith('/api/')) {
      const fixture = fixtureFor(url.pathname);
      if (!fixture) {
        throw new Error(`Synthetic performance fixture missing for ${url.pathname}`);
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(fixture),
      });
      return;
    }
    if (url.origin !== targetOrigin) {
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
}
