
import {cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createPastProjectShare, fetchPastProjectShare, updatePastProjectShare, type ProjectGridRow} from '@/features/projects/api';
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

    it('edits one legacy id-less row without overwriting its siblings', async () => {
        const legacyFirst: ProjectGridRow = {...sampleRow};
        const legacySecond: ProjectGridRow = {...addedRow};
        delete legacyFirst.id;
        delete legacySecond.id;
        const initial = shareFixture({rows: [legacyFirst, legacySecond]});
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockResolvedValue(
            shareFixture({
                rows: [
                    {...legacyFirst, team_name: 'Edited Team Alpha'},
                    legacySecond,
                ],
                version: 5,
            }),
        );

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Edit mocked row'}));

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledWith(initial.id, {
                rows: [
                    {...legacyFirst, team_name: 'Edited Team Alpha'},
                    legacySecond,
                ],
                version: 4,
            }),
        );
    });

    it('deletes only the selected legacy id-less row', async () => {
        const legacyFirst: ProjectGridRow = {...sampleRow};
        const legacySecond: ProjectGridRow = {...addedRow};
        delete legacyFirst.id;
        delete legacySecond.id;
        const initial = shareFixture({rows: [legacyFirst, legacySecond]});
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockResolvedValue(
            shareFixture({rows: [legacySecond], version: 5}),
        );

        renderPage();
        fireEvent.click(
            screen.getByRole('button', {name: 'Delete first mocked row'}),
        );

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledWith(initial.id, {
                rows: [legacySecond],
                version: 4,
            }),
        );
    });

    it('stops stale queued writes, refetches, and shows the conflict', async () => {
        const initial = shareFixture({version: 2});
        const authoritative = shareFixture({
            note: 'Remote note',
            version: 3,
        });
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockRejectedValueOnce({
            response: {
                status: 409,
                data: {
                    code: 'stale_snapshot',
                    current: authoritative,
                },
            },
        });
        vi.mocked(fetchPastProjectShare).mockResolvedValue(authoritative);

        renderPage();
        fireEvent.click(
            screen.getByRole('button', {name: 'Update mocked note'}),
        );
        fireEvent.click(
            screen.getByRole('button', {name: 'Add mocked row'}),
        );

        const conflictAlert = await screen.findByRole('alert');
        await waitFor(() =>
            expect(conflictAlert).toHaveTextContent(
                /changed elsewhere.*latest version was reloaded/i,
            ),
        );
        await waitFor(() =>
            expect(fetchPastProjectShare).toHaveBeenCalledWith(initial.id),
        );
        expect(updatePastProjectShare).toHaveBeenCalledTimes(1);
        await waitFor(() =>
            expect(screen.getByTestId('share-note')).toHaveTextContent(
                'Remote note',
            ),
        );
    });

    it('uses the reloaded version for the next edit after a conflict', async () => {
        const initial = shareFixture({version: 2});
        const authoritative = shareFixture({note: 'Remote note', version: 7});
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare)
            .mockRejectedValueOnce({
                response: {status: 409, data: {code: 'stale_snapshot'}},
            })
            .mockResolvedValueOnce(
                shareFixture({note: 'Updated note', version: 8}),
            );
        vi.mocked(fetchPastProjectShare).mockResolvedValue(authoritative);

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Update mocked note'}));

        await screen.findByText(/latest version was reloaded/i);
        fireEvent.click(screen.getByRole('button', {name: 'Update mocked note'}));

        await waitFor(() => expect(updatePastProjectShare).toHaveBeenCalledTimes(2));
        expect(updatePastProjectShare).toHaveBeenNthCalledWith(2, initial.id, {
            note: 'Updated note',
            version: 7,
        });
        await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    });

    it('blocks later writes when conflict recovery cannot reload the share', async () => {
        const initial = shareFixture({version: 2});
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockRejectedValueOnce({
            response: {status: 409, data: {code: 'stale_snapshot'}},
        });
        vi.mocked(fetchPastProjectShare).mockRejectedValue(new Error('offline'));

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Update mocked note'}));

        expect(await screen.findByRole('alert')).toHaveTextContent(
            /latest version could not be reloaded.*reload the page/i,
        );
        fireEvent.click(screen.getByRole('button', {name: 'Add mocked row'}));

        await waitFor(() => expect(fetchPastProjectShare).toHaveBeenCalledWith(initial.id));
        expect(updatePastProjectShare).toHaveBeenCalledTimes(1);
    });
});
