
import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter} from 'react-router';
import {PastProjectsPage} from '@/routes/projects/PastProjectsPage/PastProjectsPage';
import {createPastProjectShare, fetchPastProjectShare, updatePastProjectShare} from '@/features/projects/api';
import {allGridState, authState, currentRow, gridState, mockNavigate, mockRetryShare, sampleRow, sharedState} from '@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageState';
import {shareFixture, renderPage} from '@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageFixtures';

vi.mock('@/features/auth', async (importOriginal) =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).authModule(importOriginal));

vi.mock('react-router', async (importOriginal) =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).reactRouterModule(importOriginal));

vi.mock('@/features/projects/api', async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).projectsApiModule());

vi.mock('@/features/projects/hooks/data/useProjectGridData.ts', async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).useProjectGridDataModule());

vi.mock('@/features/projects', async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).projectsModule());

// The builder page's body (CatalogBuilderView) imports these two directly.
vi.mock('@/features/projects/components/curation/builder/composition/PastProjectsBuilder', async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).pastProjectsBuilderModule());
vi.mock('@/features/projects/components/curation/myCurations/MyCurationsPanel', async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).myCurationsPanelModule());

describe('PastProjectsPage', () => {
    beforeEach(() => {
        sharedState.share = null;
        sharedState.shareError = null;
        sharedState.shareNotFound = false;
        authState.user = null;
        gridState.loading = false;
        gridState.rows = [sampleRow];
        gridState.enabled = [];
        allGridState.rows = [currentRow, sampleRow];
        allGridState.enabled = [];
        mockNavigate.mockReset();
        mockRetryShare.mockReset();
        vi.mocked(createPastProjectShare).mockReset();
        vi.mocked(fetchPastProjectShare).mockReset();
        vi.mocked(updatePastProjectShare).mockReset();
    });

    afterEach(() => {
        cleanup();
    });

    it('confirms a curation the owner just saved, and only then', () => {
        sharedState.share = shareFixture();
        const saved = render(
            <MemoryRouter initialEntries={[{pathname: '/past-projects/share-abc', state: {curationSaved: true}}]}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(screen.getByText(/^Curation saved\./)).toHaveAttribute('role', 'status');
        expect(screen.getByText(/^Curation saved\./)).toHaveTextContent(
            'Curation saved. It is listed under My Curations on the Past Projects page, and you can keep editing it here.',
        );
        expect(screen.getByRole('link', {name: 'Past Projects'})).toHaveAttribute('href', '/past-projects');
        saved.unmount();

        // Opened from a link, or by someone who cannot edit it: no confirmation.
        const opened = render(
            <MemoryRouter initialEntries={['/past-projects/share-abc']}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(screen.queryByText(/Curation saved/)).toBeNull();
        opened.unmount();
        sharedState.share = shareFixture({can_edit: false});
        render(
            <MemoryRouter initialEntries={[{pathname: '/past-projects/share-abc', state: {curationSaved: true}}]}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(screen.queryByText(/Curation saved/)).toBeNull();
    });

    it('names All Projects in the saved notice of a curation All Projects saved', () => {
        sharedState.share = shareFixture();
        render(
            <MemoryRouter
                initialEntries={[
                    {pathname: '/past-projects/share-abc', state: {curationSaved: true, builtOn: '/all-projects'}},
                ]}
            >
                <PastProjectsPage/>
            </MemoryRouter>,
        );

        expect(screen.getByText(/^Curation saved\./)).toHaveTextContent(
            'Curation saved. It is listed under My Curations on the All Projects page, and you can keep editing it here.',
        );
        expect(screen.getByRole('link', {name: 'All Projects'})).toHaveAttribute('href', '/all-projects');
    });

    it('names Past Projects in the saved notice when the save names no other builder', () => {
        sharedState.share = shareFixture();
        render(
            <MemoryRouter
                initialEntries={[
                    {pathname: '/past-projects/share-abc', state: {curationSaved: true, builtOn: '/somewhere-else'}},
                ]}
            >
                <PastProjectsPage/>
            </MemoryRouter>,
        );

        expect(screen.getByRole('link', {name: 'Past Projects'})).toHaveAttribute('href', '/past-projects');
        expect(screen.queryByRole('link', {name: 'All Projects'})).toBeNull();
    });

    it('builds on the archive under the Past Projects words, without loading every project', () => {
        renderPage();

        const builder = screen.getByRole('button', {name: 'Create mocked share'});
        expect(builder).toHaveAttribute('data-catalog', 'past');
        expect(builder).toHaveAttribute('data-rows', 'Shared Project');
        expect(gridState.enabled).toContain(true);
        expect(allGridState.enabled).not.toContain(true);
    });

    it("lets a curation's owner add from every project, worded as All Projects", () => {
        sharedState.share = shareFixture();

        renderPage();

        // Every project holds whatever either builder saved, this semester's teams too.
        const search = screen.getByRole('button', {name: 'Add mocked row'});
        expect(search).toHaveAttribute('data-catalog', 'all');
        expect(search).toHaveAttribute('data-rows', 'This Semester Project|Shared Project');
        expect(allGridState.enabled).toContain(true);
        expect(gridState.enabled).not.toContain(true);
    });

    it('loads no list for a visitor who cannot edit the curation', () => {
        sharedState.share = shareFixture({can_edit: false});

        renderPage();

        expect(screen.queryByRole('button', {name: 'Add mocked row'})).toBeNull();
        expect(gridState.enabled).not.toContain(true);
        expect(allGridState.enabled).not.toContain(true);
    });

    it('passes the ?value= search on to the builder', () => {
        render(
            <MemoryRouter initialEntries={['/past-projects?value=hydroponics']}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );

        expect(screen.getByRole('button', {name: 'Create mocked share'})).toHaveAttribute(
            'data-initial-search',
            'hydroponics',
        );
    });

    it('shows a shared list with its date and a way to start a list of your own', async () => {
        sharedState.share = shareFixture();

        renderPage();

        expect(await screen.findByTestId('share-title')).toHaveAttribute('data-shared-at', '2026-06-08T00:00:00Z');
        expect(screen.queryByRole('heading', {level: 1, name: 'Past Projects'})).toBeNull();
        expect(screen.getByText(/Want to make your own list\?/)).toBeInTheDocument();
        expect(screen.getByRole('link', {name: 'Search all past projects'})).toHaveAttribute('href', '/past-projects');
    });
});
