
import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
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

    it('redirects to the shareable link route after creating a share', async () => {
        vi.mocked(createPastProjectShare).mockResolvedValue(
            shareFixture({
                version: 1,
                note: 'Review note',
            }),
        );

        renderPage();
        fireEvent.click(
            screen.getByRole('button', {name: 'Create mocked share'}),
        );

        await waitFor(() => {
            expect(createPastProjectShare).toHaveBeenCalledWith(
                [sampleRow],
                'Spring finalists',
                'Review note',
            );
            // The curation's page says it was saved.
            expect(mockNavigate).toHaveBeenCalledWith(
                '/past-projects/share-abc',
                {state: {curationSaved: true}},
            );
        });
    });

    it('renames a shared page', async () => {
        const initial = shareFixture();
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockResolvedValue(
            shareFixture({name: 'Renamed share', version: 5}),
        );

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Rename mocked share'}));

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledWith(initial.id, {
                name: 'Renamed share',
                version: 4,
            }),
        );
    });

    it("asks again whether the viewer may edit a curation once they sign out or switch accounts", () => {
        // can_edit is the server's answer for whoever was signed in when the curation loaded.
        authState.user = {member_uuid: 'owner-1'};
        sharedState.share = shareFixture();
        const {rerender} = renderPage();
        rerender(
            <MemoryRouter initialEntries={['/past-projects']}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(mockRetryShare).not.toHaveBeenCalled();

        authState.user = null;
        rerender(
            <MemoryRouter initialEntries={['/past-projects']}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(mockRetryShare).toHaveBeenCalledTimes(1);

        authState.user = {member_uuid: 'someone-else'};
        rerender(
            <MemoryRouter initialEntries={['/past-projects']}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(mockRetryShare).toHaveBeenCalledTimes(2);
    });

    it('titles a share stored without a name with the default curation title', async () => {
        sharedState.share = shareFixture({name: '  '});

        renderPage();

        expect(await screen.findByTestId('share-title')).toHaveTextContent('Past Project Curation');
    });

    it('titles a share of current-semester projects stored without a name as the server would name it', async () => {
        sharedState.share = shareFixture({name: '', rows: [sampleRow, currentRow]});

        renderPage();

        expect(await screen.findByTestId('share-title')).toHaveTextContent(/^Project Curation$/);
        expect(document.title).toBe('Project Curation | Innovate to Grow');
        expect(screen.getByRole('link', {name: 'Search all projects'})).toHaveAttribute('href', '/all-projects');
    });

    it('names the tab Past Projects even after a curation page named it', () => {
        // Both routes share the route title, so the route alone would not set it again.
        document.title = 'Spring finalists | Innovate to Grow';
        renderPage();

        expect(document.title).toBe('Past Projects | Innovate to Grow');
    });

    it('heads the builder with the archive size, the years it spans and a lede', () => {
        renderPage();

        expect(screen.getByRole('heading', {level: 1, name: 'Past Projects'})).toBeInTheDocument();
        expect(screen.getByText('1 project since 2025')).toHaveClass('itg-page-meta');
        expect(screen.getByText(/^Search past Innovate to Grow projects, check the ones you want/)).toHaveClass('itg-lead');
    });

    it('keeps the meta line in place while the archive loads, so the lede and builder do not move down', () => {
        gridState.loading = true;
        gridState.rows = [];
        const {container} = renderPage();

        const header = container.querySelector('.past-projects-header') as HTMLElement;
        const meta = header.querySelector('.itg-page-meta') as HTMLElement;
        expect(meta.textContent).toBe('\u00a0');
        expect(meta).toHaveAttribute('aria-hidden', 'true');
        expect(meta.nextElementSibling).toHaveClass('itg-lead');
    });

    it("lists the member's saved curations above the builder", () => {
        renderPage();

        const curations = screen.getByRole('region', {name: 'My Curations (mocked)'});
        const builder = screen.getByRole('button', {name: 'Create mocked share'});
        expect(curations.compareDocumentPosition(builder) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
});
