import {render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {LayoutProvider} from '@/features/layout/components/LayoutProvider/LayoutProvider';
import {useLayout} from '@/features/layout/components/LayoutProvider/context';
import type {LayoutData} from '@/features/layout/api';

const layoutApiMocks = vi.hoisted(() => ({
  fetchLayoutData: vi.fn(),
  readLayoutCache: vi.fn(),
  writeLayoutCache: vi.fn(),
}));

vi.mock('@/features/layout/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/layout/api')>();
  return {
    ...actual,
    fetchLayoutData: layoutApiMocks.fetchLayoutData,
    readLayoutCache: layoutApiMocks.readLayoutCache,
    writeLayoutCache: layoutApiMocks.writeLayoutCache,
  };
});

const layoutData = (name = 'main-nav'): LayoutData => ({
  menus: [
    {
      id: 'menu-1',
      name,
      display_name: 'Main',
      description: null,
      created_at: '',
      updated_at: '',
      items: [
        {
          type: 'app',
          title: 'Projects',
          url: '/projects',
          open_in_new_tab: false,
          children: [],
        },
      ],
    },
  ],
  footer: {
    id: 'footer-1',
    name: 'Footer',
    slug: 'footer',
    is_active: true,
    created_at: '',
    updated_at: '',
    content: {
      copyright: 'Copyright',
    },
  },
  homepage_route: '/home',
});

const LayoutProbe = () => {
  const layout = useLayout();
  return (
    <div>
      <span data-testid="state">{layout.state}</span>
      <span data-testid="menu-count">{layout.menus.length}</span>
      <span data-testid="error">{layout.error}</span>
      <span data-testid="homepage">{layout.homepage_route}</span>
    </div>
  );
};

describe('LayoutProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    layoutApiMocks.readLayoutCache.mockReturnValue(null);
    layoutApiMocks.fetchLayoutData.mockResolvedValue(layoutData());
  });

  it('hydrates from cached layout data and refreshes the cache from the API', async () => {
    layoutApiMocks.readLayoutCache.mockReturnValue(layoutData('cached-main'));
    layoutApiMocks.fetchLayoutData.mockResolvedValue(layoutData('fresh-main'));

    render(
      <LayoutProvider>
        <LayoutProbe />
      </LayoutProvider>,
    );

    expect(screen.getByTestId('state')).toHaveTextContent('ready');
    expect(screen.getByTestId('menu-count')).toHaveTextContent('1');

    await waitFor(() => expect(layoutApiMocks.writeLayoutCache).toHaveBeenCalledWith(layoutData('fresh-main')));
    expect(screen.getByTestId('homepage')).toHaveTextContent('/home');
  });

  it('loads layout data when no cache is available', async () => {
    render(
      <LayoutProvider>
        <LayoutProbe />
      </LayoutProvider>,
    );

    expect(screen.getByTestId('state')).toHaveTextContent('loading');
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('ready'));
    expect(layoutApiMocks.writeLayoutCache).toHaveBeenCalledWith(layoutData());
  });

  it('enters an error state when the initial layout request fails', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    layoutApiMocks.fetchLayoutData.mockRejectedValue(new Error('offline'));

    render(
      <LayoutProvider>
        <LayoutProbe />
      </LayoutProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('error'));
    expect(screen.getByTestId('error')).toHaveTextContent('Layout data is currently unavailable.');
    expect(errorSpy).toHaveBeenCalledWith('Failed to load layout data', expect.any(Error));
  });
});
