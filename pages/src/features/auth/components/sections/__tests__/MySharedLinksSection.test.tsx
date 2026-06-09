import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MySharedLinksSection} from '../MySharedLinksSection';

const mockListMyShares = vi.fn();
const mockDeleteShare = vi.fn();

vi.mock('@/features/projects/api', () => ({
  listMyShares: () => mockListMyShares(),
  deleteShare: (id: string) => mockDeleteShare(id),
}));

const share = (overrides = {}) => ({
  id: 'share-1',
  name: 'Spring finalists',
  note: '',
  share_url: 'https://example.test/past-projects/share-1',
  row_count: 3,
  created_at: '2026-06-05T00:00:00Z',
  ...overrides,
});

describe('MySharedLinksSection', () => {
  beforeEach(() => {
    mockListMyShares.mockReset();
    mockDeleteShare.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the list with open + delete only when the user has shares', async () => {
    mockListMyShares.mockResolvedValue([share()]);
    render(<MySharedLinksSection />);

    expect(await screen.findByText('Spring finalists')).toBeInTheDocument();
    const openLink = screen.getByRole('link', {name: /open/i});
    expect(openLink).toHaveAttribute('href', '/past-projects/share-1');
    expect(openLink).toHaveClass('account-outline-btn');
    expect(screen.queryByRole('button', {name: /copy link/i})).toBeNull();
    expect(screen.getByRole('button', {name: /delete/i})).toBeInTheDocument();
  });

  it('deletes a share after confirmation and removes it from the list', async () => {
    mockListMyShares.mockResolvedValue([share()]);
    mockDeleteShare.mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(<MySharedLinksSection />);
    await screen.findByText('Spring finalists');

    fireEvent.click(screen.getByRole('button', {name: /delete/i}));

    await waitFor(() => expect(mockDeleteShare).toHaveBeenCalledWith('share-1'));
    await waitFor(() => expect(screen.queryByText('Spring finalists')).toBeNull());
    confirmSpy.mockRestore();
  });

  it('renders nothing when the user has no shares', async () => {
    mockListMyShares.mockResolvedValue([]);
    const {container} = render(<MySharedLinksSection />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
