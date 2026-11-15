import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectCurationSharedLinksPage} from '@/features/auth/components/pages/account/sharedLinks/PastProjectCurationSharedLinksPage';

const mockUseAuth = vi.fn();
const mockListMyShares = vi.fn();
const mockDeleteShare = vi.fn();

vi.mock('@/features/auth/components/AuthContext', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/features/projects/api', () => ({
    DEFAULT_PAST_PROJECT_SHARE_NAME: 'Past Project Curation',
    listMyShares: () => mockListMyShares(),
    deleteShare: (id: string) => mockDeleteShare(id),
}));

const pagePath = '/account/past-project-curation-shared-links';

const LocationSearch = () => {
    const location = useLocation();
    return <output data-testid="destination-search">{location.search}</output>;
};

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
