
import {act, cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter} from 'react-router';
import {PastProjectsPage} from '@/routes/projects/PastProjectsPage/PastProjectsPage';
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

    it('edits a malformed legacy row using its full-fingerprint fallback key', async () => {
        const malformed: ProjectGridRow = {...sampleRow, semester_label: '', team_number: ''};
        delete malformed.id;
        const initial = shareFixture({rows: [malformed]});
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockResolvedValue(
            shareFixture({rows: [{...malformed, team_name: 'Edited Team Alpha'}], version: 5}),
        );

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Edit mocked row'}));

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledWith(initial.id, {
                rows: [{...malformed, team_name: 'Edited Team Alpha'}],
                version: 4,
            }),
        );
    });

    it('rebases a submitted row addition into the current share', async () => {
        const initial = shareFixture();
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockResolvedValue(
            shareFixture({rows: [sampleRow, addedRow], version: 5}),
        );

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Edit with added row'}));

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledWith(initial.id, {
                rows: [sampleRow, addedRow],
                version: 4,
            }),
        );
    });

    it('reorders survivor rows when the submitted order changes', async () => {
        const initial = shareFixture({rows: [sampleRow, addedRow]});
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockResolvedValue(
            shareFixture({rows: [addedRow, sampleRow], version: 5}),
        );

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Reverse mocked rows'}));

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledWith(initial.id, {
                rows: [addedRow, sampleRow],
                version: 4,
            }),
        );
    });

    it('rethrows non-conflict mutation errors without showing a conflict', async () => {
        const initial = shareFixture();
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare)
            .mockRejectedValueOnce('boom')
            .mockRejectedValueOnce(new Error('network down'));

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Update mocked note'}));
        await waitFor(() => expect(updatePastProjectShare).toHaveBeenCalledTimes(1));

        fireEvent.click(screen.getByRole('button', {name: 'Update mocked note'}));
        await waitFor(() => expect(updatePastProjectShare).toHaveBeenCalledTimes(2));

        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('skips the network call when a submitted patch is empty', async () => {
        const initial = shareFixture();
        sharedState.share = initial;

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'No-op update'}));

        await act(async () => {});
        expect(updatePastProjectShare).not.toHaveBeenCalled();
    });

    it('does not store the fallback title as the name when a blank-name share is edited', async () => {
        const initial = shareFixture({name: ''});
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockResolvedValue(
            shareFixture({name: '', note: 'Updated note', version: 5}),
        );

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Update mocked note'}));

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledWith(initial.id, {
                note: 'Updated note',
                version: 4,
            }),
        );
    });

    it('sends a cleared name so the server derives the default again', async () => {
        const initial = shareFixture();
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockResolvedValue(
            shareFixture({name: 'Past Project Curation', version: 5}),
        );

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Clear mocked name'}));

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledWith(initial.id, {name: '', version: 4}),
        );
    });

    it('adds only projects the current share does not have yet', async () => {
        // The project landed in the share (another tab, a reloaded conflict) while the add loaded details.
        sharedState.share = shareFixture({rows: [sampleRow, addedRow]});

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Add mocked row'}));

        await act(async () => {});
        expect(updatePastProjectShare).not.toHaveBeenCalled();
    });

    it('resets overrides and mutation state when switching to a different share', async () => {
        sharedState.share = shareFixture({note: 'first'});
        const {rerender} = renderPage();
        expect(await screen.findByTestId('share-note')).toHaveTextContent('first');

        sharedState.share = shareFixture({id: 'share-def', note: 'second'});
        rerender(
            <MemoryRouter initialEntries={['/past-projects']}>
                <PastProjectsPage />
            </MemoryRouter>,
        );

        expect(await screen.findByTestId('share-note')).toHaveTextContent('second');
    });
});
