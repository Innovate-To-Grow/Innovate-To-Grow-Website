import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {StrictMode} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {FooterContentResponse, Menu} from '@/features/layout/api';
import {LayoutProvider} from '@/features/layout/components/LayoutProvider/LayoutProvider';
import {useLayout} from '@/features/layout/components/LayoutProvider/context';

const layoutApi = vi.hoisted(() => ({
  fetchLayoutData: vi.fn(),
  readLayoutCache: vi.fn(),
  writeLayoutCache: vi.fn(),
}));

vi.mock('@/features/layout/api', () => layoutApi);

const makeMenu = (name: string): Menu => ({
  id: `menu-${name}`,
  name,
  display_name: name,
  description: null,
  items: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

const makeFooter = (): FooterContentResponse => ({
  id: 'footer-id',
  name: 'Footer',
  slug: 'footer',
  content: {},
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

const makeData = () => ({
  menus: [makeMenu('main')],
  footer: makeFooter(),
});

const Harness = () => {
  const {state, menus, footer, error} = useLayout();
  return (
    <div>
      <span data-testid="state">{state}</span>
      <span data-testid="menus">{menus.map((m) => m.name).join(',')}</span>
      <span data-testid="footer">{footer ? footer.name : 'none'}</span>
      <span data-testid="error">{error ?? ''}</span>
    </div>
  );
};

describe('LayoutProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    layoutApi.readLayoutCache.mockReturnValue(null);
    layoutApi.fetchLayoutData.mockResolvedValue(makeData());
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('loads layout data from the network when no cache exists', async () => {
    const data = makeData();
    layoutApi.fetchLayoutData.mockResolvedValue(data);

    render(
      <LayoutProvider>
        <Harness />
      </LayoutProvider>,
    );

    expect(screen.getByTestId('state')).toHaveTextContent('loading');

    await waitFor(() =>
      expect(screen.getByTestId('state')).toHaveTextContent('ready'),
    );
    expect(screen.getByTestId('menus')).toHaveTextContent('main');
    expect(screen.getByTestId('footer')).toHaveTextContent('Footer');
    expect(screen.getByTestId('error')).toHaveTextContent('');
    expect(layoutApi.writeLayoutCache).toHaveBeenCalledWith(data);
  });

  it('hydrates a ready state from cache while refreshing in the background', async () => {
    const cached = makeData();
    layoutApi.readLayoutCache.mockReturnValue(cached);
    let resolveFetch!: (value: ReturnType<typeof makeData>) => void;
    layoutApi.fetchLayoutData.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );

    render(
      <LayoutProvider>
        <Harness />
      </LayoutProvider>,
    );

    expect(screen.getByTestId('state')).toHaveTextContent('ready');
    expect(screen.getByTestId('menus')).toHaveTextContent('main');

    await act(async () => resolveFetch(makeData()));
    expect(layoutApi.writeLayoutCache).toHaveBeenCalledTimes(1);
  });

  it('sets an error state when the initial fetch fails', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    layoutApi.fetchLayoutData.mockRejectedValue(new Error('network down'));

    render(
      <LayoutProvider>
        <Harness />
      </LayoutProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId('state')).toHaveTextContent('error'),
    );
    expect(screen.getByTestId('error')).toHaveTextContent(
      'Layout data is currently unavailable.',
    );
    expect(consoleError).toHaveBeenCalled();
  });

  it('keeps cached data when a background refresh fails', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    layoutApi.readLayoutCache.mockReturnValue(makeData());
    layoutApi.fetchLayoutData.mockRejectedValue(new Error('network down'));

    render(
      <LayoutProvider>
        <Harness />
      </LayoutProvider>,
    );

    expect(screen.getByTestId('state')).toHaveTextContent('ready');
    await waitFor(() => expect(consoleError).toHaveBeenCalled());
    expect(screen.getByTestId('state')).toHaveTextContent('ready');
    expect(screen.getByTestId('error')).toHaveTextContent('');
    expect(layoutApi.writeLayoutCache).not.toHaveBeenCalled();
  });

  it('ignores a response that arrives after unmount', async () => {
    let resolveFetch!: (value: ReturnType<typeof makeData>) => void;
    layoutApi.fetchLayoutData.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );

    const {unmount} = render(
      <LayoutProvider>
        <Harness />
      </LayoutProvider>,
    );
    unmount();

    await act(async () => resolveFetch(makeData()));
    expect(layoutApi.writeLayoutCache).not.toHaveBeenCalled();
  });

  it('deduplicates a second load while a request is in flight', async () => {
    let resolveFetch!: (value: ReturnType<typeof makeData>) => void;
    layoutApi.fetchLayoutData.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );

    render(
      <StrictMode>
        <LayoutProvider>
          <Harness />
        </LayoutProvider>
      </StrictMode>,
    );

    expect(layoutApi.fetchLayoutData).toHaveBeenCalledTimes(1);

    await act(async () => resolveFetch(makeData()));
    await waitFor(() =>
      expect(screen.getByTestId('state')).toHaveTextContent('ready'),
    );
  });
});
