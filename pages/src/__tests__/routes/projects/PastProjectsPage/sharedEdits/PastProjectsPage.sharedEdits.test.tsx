
import {act, cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createPastProjectShare, fetchPastProjectShare, updatePastProjectShare, type PastProjectShare} from '@/features/projects/api';
import {addedRow, mockNavigate, mockRetryShare, sampleRow, sharedState} from '@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageState';
import {shareFixture, renderPage} from '@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageFixtures';

vi.mock('react-router', async (importOriginal) =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).reactRouterModule(importOriginal));

vi.mock('@/features/projects/api', async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).projectsApiModule());

vi.mock('@/features/projects/hooks/data/useProjectGridData.ts', async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).sharedEditsUseProjectGridDataModule());

vi.mock('@/features/projects', async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).projectsModule());

// The builder page's body (CatalogBuilderView) imports these two directly.
vi.mock('@/features/projects/components/curation/builder/composition/PastProjectsBuilder', async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).pastProjectsBuilderModule());
vi.mock('@/features/projects/components/curation/myCurations/MyCurationsPanel', async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageMocks')).myCurationsPanelModule());

describe('PastProjectsPage — editing a shared list', () => {
    beforeEach(() => {
        sharedState.share = null;
        sharedState.shareError = null;
        sharedState.shareNotFound = false;
        mockNavigate.mockReset();
        mockRetryShare.mockReset();
        vi.mocked(createPastProjectShare).mockReset();
        vi.mocked(fetchPastProjectShare).mockReset();
        vi.mocked(updatePastProjectShare).mockReset();
    });

    afterEach(() => {
        cleanup();
    });

    it('serializes PATCHes and advances the optimistic version for queued edits', async () => {
        const initial = shareFixture();
        sharedState.share = initial;
        let resolveFirst!: (share: PastProjectShare) => void;
        vi.mocked(updatePastProjectShare)
            .mockReturnValueOnce(
                new Promise((resolve) => {
                    resolveFirst = resolve;
                }),
            )
            .mockResolvedValueOnce(
                shareFixture({
                    rows: [sampleRow, addedRow],
                    note: 'Updated note',
                    version: 6,
                }),
            );

        renderPage();
        fireEvent.click(
            screen.getByRole('button', {name: 'Update mocked note'}),
        );
        fireEvent.click(
            screen.getByRole('button', {name: 'Add mocked row'}),
        );

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledTimes(1),
        );
        expect(updatePastProjectShare).toHaveBeenNthCalledWith(
            1,
            initial.id,
            {note: 'Updated note', version: 4},
        );

        await act(async () => {
            resolveFirst(
                shareFixture({note: 'Updated note', version: 5}),
            );
            await Promise.resolve();
        });

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledTimes(2),
        );
        expect(updatePastProjectShare).toHaveBeenNthCalledWith(
            2,
            initial.id,
            {
                rows: [sampleRow, addedRow],
                version: 5,
            },
        );
    });

    it('rebases a queued stale row edit without erasing an in-flight row addition', async () => {
        const initial = shareFixture();
        sharedState.share = initial;
        let resolveAddition!: (share: PastProjectShare) => void;
        vi.mocked(updatePastProjectShare)
            .mockReturnValueOnce(
                new Promise((resolve) => {
                    resolveAddition = resolve;
                }),
            )
            .mockResolvedValueOnce(
                shareFixture({
                    rows: [
                        {...sampleRow, team_name: 'Edited Team Alpha'},
                        addedRow,
                    ],
                    version: 6,
                }),
            );

        renderPage();
        fireEvent.click(
            screen.getByRole('button', {name: 'Add mocked row'}),
        );
        fireEvent.click(
            screen.getByRole('button', {name: 'Edit mocked row'}),
        );

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledTimes(1),
        );
        expect(updatePastProjectShare).toHaveBeenNthCalledWith(
            1,
            initial.id,
            {
                rows: [sampleRow, addedRow],
                version: 4,
            },
        );

        await act(async () => {
            resolveAddition(
                shareFixture({
                    rows: [sampleRow, addedRow],
                    version: 5,
                }),
            );
            await Promise.resolve();
        });

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledTimes(2),
        );
        expect(updatePastProjectShare).toHaveBeenNthCalledWith(
            2,
            initial.id,
            {
                rows: [
                    {...sampleRow, team_name: 'Edited Team Alpha'},
                    addedRow,
                ],
                version: 5,
            },
        );
    });
});
