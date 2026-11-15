
import {cleanup, fireEvent, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createPastProjectShare, fetchPastProjectShare, updatePastProjectShare} from '@/features/projects/api';
import {allGridState, authState, currentRow, gridState, mockNavigate, mockRetryShare, sampleRow, sharedState} from '@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageState';
import {renderPage} from '@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageFixtures';

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

    it('explains a shared list that does not exist', () => {
        sharedState.shareError = 'Request failed with status code 404';
        sharedState.shareNotFound = true;

        renderPage();

        // The curation did not load, so the page cannot say which list it came from: a neutral eyebrow, and All
        // Projects, which searches both lists.
        expect(screen.getByText('Curation', {selector: '.itg-eyebrow'})).toBeInTheDocument();
        expect(screen.queryByText(/Curation · /)).toBeNull();
        expect(screen.getByRole('heading', {level: 1, name: "This curation isn't available"})).toBeInTheDocument();
        expect(screen.getByText(/or search all projects yourself\.$/)).toBeInTheDocument();
        const search = screen.getByRole('link', {name: 'Search All Projects'});
        expect(search).toHaveAttribute('href', '/all-projects');
        expect(search).toHaveClass('itg-btn', 'itg-btn-primary');
        expect(screen.getByRole('link', {name: 'Go to Projects'})).toHaveAttribute('href', '/projects');
        expect(screen.queryByRole('link', {name: /past projects/i})).toBeNull();
        expect(screen.queryByRole('button', {name: 'Try Again'})).toBeNull();
        expect(screen.queryByTestId('share-title')).toBeNull();
    });

    it('offers to try again, without calling the link wrong, when a shared list fails to load', () => {
        sharedState.shareError = 'Request failed with status code 503';
        sharedState.shareNotFound = false;

        renderPage();

        expect(screen.getByText('Curation', {selector: '.itg-eyebrow'})).toBeInTheDocument();
        expect(screen.getByRole('heading', {level: 1, name: "We couldn't load this curation"})).toBeInTheDocument();
        expect(screen.queryByRole('heading', {name: "This curation isn't available"})).toBeNull();
        expect(screen.queryByText(/deleted the list/)).toBeNull();
        // Try Again is the page's one primary action; the way on is a text link.
        expect(screen.getByRole('button', {name: 'Try Again'})).toHaveClass('itg-btn', 'itg-btn-primary');
        const search = screen.getByRole('link', {name: 'Search All Projects'});
        expect(search).toHaveAttribute('href', '/all-projects');
        expect(search).toHaveClass('itg-link');
        expect(search).not.toHaveClass('itg-btn');
        expect(screen.queryByTestId('share-title')).toBeNull();

        fireEvent.click(screen.getByRole('button', {name: 'Try Again'}));
        expect(mockRetryShare).toHaveBeenCalledTimes(1);
    });
});
