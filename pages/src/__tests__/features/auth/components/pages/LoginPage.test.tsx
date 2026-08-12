import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {LoginPage} from '@/features/auth/components/pages/LoginPage';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth/components/AuthContext', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/features/auth/components/forms/LoginForm', () => ({
    LoginForm: ({returnTo}: { returnTo?: string | null }) => <output data-testid="login-return-to">{returnTo}</output>,
}));

const Destination = ({name}: { name: string }) => {
    const location = useLocation();
    return <><p>{name}</p>
        <output data-testid="destination-search">{location.search}</output>
    </>;
};

const renderPage = (entry: string) => render(
    <MemoryRouter initialEntries={[entry]}>
        <Routes>
            <Route path="/login" element={<LoginPage/>}/>
            <Route path="/account" element={<Destination name="Account Page"/>}/>
            <Route path="/past-projects/:shareId" element={<Destination name="Shared Projects"/>}/>
            <Route path="/complete-profile" element={<Destination name="Complete Profile"/>}/>
        </Routes>
    </MemoryRouter>,
);

describe('LoginPage returnTo handling', () => {
    beforeEach(() => {
        mockUseAuth.mockReset();
    });

    afterEach(cleanup);

    it('passes a safe internal returnTo to the login form', () => {
        mockUseAuth.mockReturnValue({isAuthenticated: false, requiresProfileCompletion: false});

        renderPage('/login?returnTo=%2Fpast-projects%2Fshare-123');

        expect(screen.getByTestId('login-return-to')).toHaveTextContent('/past-projects/share-123');
    });

    it('returns an authenticated visitor to the requested page', async () => {
        mockUseAuth.mockReturnValue({isAuthenticated: true, requiresProfileCompletion: false});

        renderPage('/login?returnTo=%2Fpast-projects%2Fshare-123');

        expect(await screen.findByText('Shared Projects')).toBeInTheDocument();
    });

    it('preserves returnTo through required profile completion', async () => {
        mockUseAuth.mockReturnValue({isAuthenticated: true, requiresProfileCompletion: true});

        renderPage('/login?returnTo=%2Fpast-projects%2Fshare-123');

        expect(await screen.findByText('Complete Profile')).toBeInTheDocument();
        expect(screen.getByTestId('destination-search')).toHaveTextContent(
            '?returnTo=%2Fpast-projects%2Fshare-123',
        );
    });

    it('rejects an external returnTo and falls back to account', async () => {
        mockUseAuth.mockReturnValue({isAuthenticated: true, requiresProfileCompletion: false});

        renderPage('/login?returnTo=https%3A%2F%2Fevil.example%2Fphish');

        expect(await screen.findByText('Account Page')).toBeInTheDocument();
    });

});
