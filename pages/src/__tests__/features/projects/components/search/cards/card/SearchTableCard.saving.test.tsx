import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SearchTableCard, type SearchTableSaveHelpers, type SearchTableSaveResult} from '@/features/projects/components/search/cards/SearchTableCard';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {deferred, makeRow, makeRows, rowCheckbox} from '@/__tests__/features/projects/components/search/cards/card/searchTableCardFixtures';

const renderCard = (props: Partial<Parameters<typeof SearchTableCard>[0]> = {}) =>
    render(
        <SearchTableCard
            canRemove
            initialRows={makeRows()}
            tableId="table-1"
            title="Search Table"
            onRemove={vi.fn()}
            onMergeSelected={vi.fn()}
            {...props}
        />,
    );

describe('SearchTableCard', () => {
    afterEach(() => {
        cleanup();
    });

    it('saves the checked rows and clears the selection on success', async () => {
        const onMergeSelected = vi.fn().mockResolvedValue({tone: 'success', message: '1 project added.'});
        renderCard({onMergeSelected});

        fireEvent.click(rowCheckbox('Project 2'));
        const mergeButton = screen.getByRole('button', {name: 'Add to Curation'});
        expect(mergeButton).not.toHaveAttribute('aria-disabled');

        fireEvent.click(mergeButton);

        await waitFor(() => expect(onMergeSelected).toHaveBeenCalledTimes(1));
        const [rowsArg] = onMergeSelected.mock.calls[0];
        expect(rowsArg).toHaveLength(1);
        expect(rowsArg[0]).toMatchObject({project_title: 'Project 2'});
        expect(rowsArg[0]).not.toHaveProperty('__key');

        await waitFor(() => expect(screen.getByRole('button', {name: 'Add to Curation'})).toHaveAttribute('aria-disabled', 'true'));
        expect(rowCheckbox('Project 2')).not.toBeChecked();
    });

    it('reports a synchronous save inside the table straight away', () => {
        const onMergeSelected = vi.fn(
            (): SearchTableSaveResult => ({tone: 'info', message: 'That project is already in the curation draft.'}),
        );
        renderCard({onMergeSelected});

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

        expect(screen.getByRole('status')).toHaveTextContent('That project is already in the curation draft.');
        expect(rowCheckbox('Project 1')).not.toBeChecked();
        expect(screen.getByRole('button', {name: 'Add to Curation'})).toHaveAttribute('aria-disabled', 'true');
    });

    it('keeps only the retained rows checked and shows the error beside the toolbar', async () => {
        const onMergeSelected = vi.fn().mockResolvedValue({
            tone: 'error',
            message: '1 project could not be loaded and is still selected. Click Add to Curation to try again.',
            retainedIndexes: [1],
        } satisfies SearchTableSaveResult);
        renderCard({onMergeSelected});

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(rowCheckbox('Project 3'));
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

        await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('1 project could not be loaded'));
        expect(screen.getByText(/^1 project could not be loaded/, {selector: 'span'})).toBeVisible();
        // Rows are submitted in table order; index 1 is Project 3.
        expect(rowCheckbox('Project 1')).not.toBeChecked();
        expect(rowCheckbox('Project 3')).toBeChecked();
    });

    it('keeps the whole selection and explains when the save rejects', async () => {
        renderCard({onMergeSelected: vi.fn().mockRejectedValue(new Error('boom'))});

        fireEvent.click(rowCheckbox('Project 2'));
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

        await waitFor(() =>
            expect(screen.getByRole('alert')).toHaveTextContent('Could not add the selected projects.'),
        );
        expect(rowCheckbox('Project 2')).toBeChecked();
    });

    it('shows progress while a save runs, blocks a second save, and keeps rows checked meanwhile', async () => {
        const pending = deferred<SearchTableSaveResult>();
        let helpers: SearchTableSaveHelpers | undefined;
        const onMergeSelected = vi.fn((_rows: ProjectGridRow[], saveHelpers: SearchTableSaveHelpers) => {
            helpers = saveHelpers;
            return pending.promise;
        });
        const onViewMergedResults = vi.fn();
        renderCard({onMergeSelected, onViewMergedResults});

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(rowCheckbox('Project 2'));
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

        expect(helpers?.tableId).toBe('table-1');
        // aria-disabled rather than disabled, so keyboard focus stays on the pressed button.
        const savingButton = screen.getByRole('button', {name: 'Adding…'});
        expect(savingButton).toHaveAttribute('aria-disabled', 'true');
        expect(savingButton).toBeEnabled();
        expect(screen.getByRole('status')).toHaveTextContent('Adding 2 projects…');
        // Progress shows for larger loads only, in steps, and stays out of the live region. It counts settled
        // requests, so it is worded as progress rather than as a number of loaded projects.
        act(() => helpers?.reportProgress(8, 40));
        expect(screen.getByText(/Loading details: 8 of 40\./)).toBeInTheDocument();
        expect(screen.getByRole('status')).not.toHaveTextContent('Loading details');
        // Tidying the table while it saves would contradict the outcome it is about to report.
        expect(screen.getByRole('button', {name: 'Remove from Table'})).toHaveAttribute('aria-disabled', 'true');
        expect(screen.getByRole('button', {name: 'Delete Table: Search Table'})).toBeDisabled();

        // Checked while the save is running: must survive the save finishing.
        fireEvent.click(rowCheckbox('Project 3'));
        fireEvent.click(savingButton);
        expect(onMergeSelected).toHaveBeenCalledTimes(1);

        await act(async () => {
            pending.resolve({tone: 'success', message: '2 projects added to the curation draft (2 in total).'});
        });

        expect(screen.getByRole('status')).toHaveTextContent('2 projects added to the curation draft');
        expect(screen.getByRole('button', {name: 'Add to Curation'})).not.toHaveAttribute('aria-disabled');
        expect(rowCheckbox('Project 1')).not.toBeChecked();
        expect(rowCheckbox('Project 2')).not.toBeChecked();
        expect(rowCheckbox('Project 3')).toBeChecked();

        fireEvent.click(screen.getByRole('button', {name: 'View Curation Draft'}));
        expect(onViewMergedResults).toHaveBeenCalledTimes(1);
    });

    it('keeps every submitted row checked when an error result names no retained rows', async () => {
        renderCard({onMergeSelected: vi.fn().mockResolvedValue({tone: 'error', message: 'Boom'})});

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(rowCheckbox('Project 2'));
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

        await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Boom'));
        expect(rowCheckbox('Project 1')).toBeChecked();
        expect(rowCheckbox('Project 2')).toBeChecked();
    });

    it('asks before saving a very large selection', async () => {
        const onMergeSelected = vi.fn().mockResolvedValue({tone: 'success', message: 'Saved.'});
        const rows = Array.from({length: 120}, (_, index) =>
            makeRow({team_number: `T${index}`, project_title: `Bulk ${index}`}),
        );
        renderCard({initialRows: rows, onMergeSelected});

        fireEvent.click(screen.getByRole('button', {name: 'Select All'}));
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));
        const dialog = screen.getByRole('dialog', {name: 'Add 120 projects?'});
        expect(onMergeSelected).not.toHaveBeenCalled();

        fireEvent.click(within(dialog).getByRole('button', {name: 'Cancel'}));
        expect(onMergeSelected).not.toHaveBeenCalled();
        expect(rowCheckbox('Bulk 0')).toBeChecked();

        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));
        fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Add 120 Projects'}));
        await waitFor(() => expect(onMergeSelected).toHaveBeenCalledTimes(1));
        expect(onMergeSelected.mock.calls[0][0]).toHaveLength(120);
    });
});
