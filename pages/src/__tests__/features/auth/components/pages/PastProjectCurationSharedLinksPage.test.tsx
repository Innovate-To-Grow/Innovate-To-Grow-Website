import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectCurationSharedLinksPage} from '@/features/auth/components/pages/PastProjectCurationSharedLinksPage';

const mockUseAuth = vi.fn();
const mockListMyShares = vi.fn();
const mockDeleteShare = vi.fn();

vi.mock('@/features/auth/components/AuthContext', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/features/projects/api', () => ({
    listMyShares: () => mockListMyShares(),
    deleteShare: (id: string) => mockDeleteShare(id),
}));

const pagePath = '/account/past-project-curation-shared-links';

const LocationSearch = () => {
    const location = useLocation();
    return <output data-testid="destination-search">{location.search}</output>;
};

const share = (overrides = {}) => ({
    id: 'share-1',
    name: 'Spring finalists',
    note: '',
    version: 1,
    share_url: 'https://example.test/past-projects/share-1',
    row_count: 3,
    created_at: '2026-06-05T00:00:00Z',
    ...overrides,
});

const renderPage = () => render(
    <MemoryRouter initialEntries={[pagePath]}>
        <Routes>
            <Route path={pagePath} element={<PastProjectCurationSharedLinksPage/>}/>
            <Route path="/login" element={<><p>Login Page</p><LocationSearch/></>}/>
            <Route path="/complete-profile" element={<><p>Complete Profile Page</p><LocationSearch/></>}/>
        </Routes>
    </MemoryRouter>,
);

describe('PastProjectCurationSharedLinksPage', () => {
    beforeEach(() => {
        mockUseAuth.mockReset();
        mockListMyShares.mockReset();
        mockDeleteShare.mockReset();

        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
            requiresProfileCompletion: false,
        });
    });

    afterEach(() => {
        cleanup();
        vi.restoreAllMocks();
    });

    it('renders all shared links with open and delete actions', async () => {
        mockListMyShares.mockResolvedValue([
            share(),
            share({id: 'share-2', name: 'Fall demo set', row_count: 1, created_at: '2026-06-09T00:00:00Z'}),
        ]);

        renderPage();

        expect(await screen.findByRole('heading', {
            level: 1,
            name: 'Past Project Curation Shared Links'
        })).toBeInTheDocument();
        expect(screen.getByText('Spring finalists')).toBeInTheDocument();
        expect(screen.getByText('Fall demo set')).toBeInTheDocument();
        expect(screen.getByText('2 of 2 shared links')).toBeInTheDocument();

        const openLinks = screen.getAllByRole('link', {name: /open/i});
        expect(openLinks[0]).toHaveAttribute('href', '/past-projects/share-1');
        expect(openLinks[1]).toHaveAttribute('href', '/past-projects/share-2');
        expect(screen.getAllByRole('button', {name: /delete/i})).toHaveLength(2);
    });

    it('filters shared links by search text including hidden notes', async () => {
        mockListMyShares.mockResolvedValue([
            share({id: 'share-1', name: 'Spring finalists', note: 'student teams'}),
            share({id: 'share-2', name: 'Industry archive', note: 'robotics cohort'}),
        ]);

        renderPage();
        await screen.findByText('Spring finalists');

        fireEvent.change(screen.getByLabelText(/search shared links/i), {target: {value: 'robotics'}});

        expect(screen.queryByText('Spring finalists')).toBeNull();
        expect(screen.getByText('Industry archive')).toBeInTheDocument();
        expect(screen.getByText('1 of 2 shared links')).toBeInTheDocument();
    });

    it('shows a no-match state without losing the source links', async () => {
        mockListMyShares.mockResolvedValue([share()]);

        renderPage();
        await screen.findByText('Spring finalists');

        fireEvent.change(screen.getByLabelText(/search shared links/i), {target: {value: 'missing cohort'}});

        expect(screen.getByText('No shared links match your search.')).toBeInTheDocument();
        expect(screen.getByText('0 of 1 shared links')).toBeInTheDocument();

        fireEvent.change(screen.getByLabelText(/search shared links/i), {target: {value: ''}});
        expect(screen.getByText('Spring finalists')).toBeInTheDocument();
    });

    it('shows an empty state when the account has no shared links', async () => {
        mockListMyShares.mockResolvedValue([]);

        renderPage();

        expect(await screen.findByText('No Past Project Curation Shared Links yet.')).toBeInTheDocument();
        expect(screen.getByText('0 of 0 shared links')).toBeInTheDocument();
    });

    it('shows a load error instead of an empty state when shares fail to load', async () => {
        mockListMyShares.mockRejectedValue({response: {status: 500, data: {detail: 'Server unavailable'}}});

        renderPage();

        expect(await screen.findByText('Server unavailable')).toBeInTheDocument();
        expect(screen.queryByText('No Past Project Curation Shared Links yet.')).toBeNull();
    });

    it('deletes a shared link after confirmation', async () => {
        mockListMyShares.mockResolvedValue([share()]);
        mockDeleteShare.mockResolvedValue(undefined);
        vi.spyOn(window, 'confirm').mockReturnValue(true);

        renderPage();
        await screen.findByText('Spring finalists');

        fireEvent.click(screen.getByRole('button', {name: /delete/i}));

        await waitFor(() => expect(mockDeleteShare).toHaveBeenCalledWith('share-1'));
        await waitFor(() => expect(screen.queryByText('Spring finalists')).toBeNull());
        expect(await screen.findByText('Shared link deleted.')).toBeInTheDocument();
    });

    it('keeps a shared link when deletion is cancelled', async () => {
        mockListMyShares.mockResolvedValue([share()]);
        vi.spyOn(window, 'confirm').mockReturnValue(false);

        renderPage();
        await screen.findByText('Spring finalists');

        fireEvent.click(screen.getByRole('button', {name: /delete/i}));

        expect(mockDeleteShare).not.toHaveBeenCalled();
        expect(screen.getByText('Spring finalists')).toBeInTheDocument();
        expect(screen.queryByText('Shared link deleted.')).toBeNull();
    });

    it('keeps a shared link and surfaces the API error when deletion fails', async () => {
        mockListMyShares.mockResolvedValue([share()]);
        mockDeleteShare.mockRejectedValue({response: {status: 500, data: {detail: 'Delete unavailable'}}});
        vi.spyOn(window, 'confirm').mockReturnValue(true);

        renderPage();
        await screen.findByText('Spring finalists');
        fireEvent.click(screen.getByRole('button', {name: /delete/i}));

        expect(await screen.findByText('Delete unavailable')).toBeInTheDocument();
        expect(screen.getByText('Spring finalists')).toBeInTheDocument();
        expect(screen.queryByText('Shared link deleted.')).toBeNull();
    });

    it('redirects unauthenticated users to login without loading shares', async () => {
        mockUseAuth.mockReturnValue({
            isAuthenticated: false,
            requiresProfileCompletion: false,
        });

        renderPage();

        expect(await screen.findByText('Login Page')).toBeInTheDocument();
        expect(screen.getByTestId('destination-search')).toHaveTextContent(
            `?returnTo=${encodeURIComponent(pagePath)}`,
        );
        expect(mockListMyShares).not.toHaveBeenCalled();
    });

    it('redirects incomplete profiles back through profile completion without loading shares', async () => {
        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
            requiresProfileCompletion: true,
        });

        renderPage();

        expect(await screen.findByText('Complete Profile Page')).toBeInTheDocument();
        expect(screen.getByTestId('destination-search')).toHaveTextContent(
            `?returnTo=${encodeURIComponent(pagePath)}`,
        );
        expect(mockListMyShares).not.toHaveBeenCalled();
    });
});
