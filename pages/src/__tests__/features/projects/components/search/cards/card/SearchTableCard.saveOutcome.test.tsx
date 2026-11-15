import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SearchTableCard, type SearchTableSaveResult} from '@/features/projects/components/search/cards/SearchTableCard';
import {cardSection, deferred, makeRow, makeRows, rowCheckbox} from '@/__tests__/features/projects/components/search/cards/card/searchTableCardFixtures';

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

    it('keeps focus where the user put it while the large-save dialog is open', () => {
        const rows = Array.from({length: 120}, (_, index) =>
            makeRow({team_number: `T${index}`, project_title: `Bulk ${index}`}),
        );
        const props = {
            canRemove: true,
            initialRows: rows,
            tableId: 'table-1',
            title: 'Search Table',
            onRemove: vi.fn(),
            onMergeSelected: vi.fn(),
        };
        const {rerender} = render(<SearchTableCard {...props} />);
        fireEvent.click(screen.getByRole('button', {name: 'Select All'}));
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));
        const dialog = screen.getByRole('dialog', {name: 'Add 120 projects?'});
        expect(within(dialog).getByRole('button', {name: 'Add 120 Projects'})).toHaveFocus();

        const cancel = within(dialog).getByRole('button', {name: 'Cancel'});
        cancel.focus();
        // Another table's save finishing re-renders every card.
        rerender(<SearchTableCard {...props} isRowSaved={() => false} />);
        expect(cancel).toHaveFocus();
        fireEvent.keyDown(window, {key: 'Escape'});
        expect(screen.queryByRole('dialog')).toBeNull();
        expect(props.onMergeSelected).not.toHaveBeenCalled();
    });

    it('repeats Save under long pages and reports the outcome next to the button used', async () => {
        const onMergeSelected = vi.fn((): SearchTableSaveResult => ({tone: 'success', message: 'Saved from below.'}));
        const rows = Array.from({length: 12}, (_, index) => makeRow({team_number: `T${index}`, project_title: `Row ${index}`}));
        const {container} = renderCard({initialRows: rows, onMergeSelected});
        expect(container.querySelector('.search-table-bottom-actions')).toBeNull();

        fireEvent.change(screen.getByLabelText('Per page'), {target: {value: '25'}});
        const bottom = container.querySelector('.search-table-bottom-actions') as HTMLElement;
        expect(bottom).not.toBeNull();

        fireEvent.click(rowCheckbox('Row 3'));
        expect(within(bottom).getByText('1 selected')).toBeInTheDocument();
        fireEvent.click(within(bottom).getByRole('button', {name: 'Add to Curation'}));

        expect(within(bottom).getByText('Saved from below.')).toBeInTheDocument();
        expect(container.querySelector('.project-grid-toolbar .search-table-save-status')).toBeNull();
    });

    it('moves the outcome to the top Save button once the bottom one is gone', async () => {
        const pending = deferred<SearchTableSaveResult>();
        const rows = Array.from({length: 12}, (_, index) => makeRow({team_number: `T${index}`, project_title: `Row ${index}`}));
        const {container} = renderCard({initialRows: rows, onMergeSelected: () => pending.promise});
        fireEvent.change(screen.getByLabelText('Per page'), {target: {value: '25'}});
        fireEvent.click(rowCheckbox('Row 3'));
        const bottom = container.querySelector('.search-table-bottom-actions') as HTMLElement;
        fireEvent.click(within(bottom).getByRole('button', {name: 'Add to Curation'}));

        // The page shrinks below the bottom Save while the save runs.
        fireEvent.change(within(cardSection(container)).getByRole('searchbox'), {target: {value: 'Row 1'}});
        await waitFor(() => expect(container.querySelector('.search-table-bottom-actions')).toBeNull());
        await act(async () => pending.resolve({tone: 'error', message: 'Row 3 could not be loaded.', retainedIndexes: [0]}));

        const toolbarStatus = container.querySelector('.project-grid-toolbar .search-table-save-status') as HTMLElement;
        expect(within(toolbarStatus).getByText('Row 3 could not be loaded.')).toBeVisible();
        expect(screen.getByRole('alert')).toHaveTextContent('Row 3 could not be loaded.');
    });

    it('reports the checked rows that are still waiting to be saved', async () => {
        const onSelectionChange = vi.fn();
        const pending = deferred<SearchTableSaveResult>();
        renderCard({onSelectionChange, onMergeSelected: () => pending.promise});

        fireEvent.click(rowCheckbox('Project 1'));
        expect(onSelectionChange).toHaveBeenLastCalledWith(
            'table-1',
            [expect.objectContaining({project_title: 'Project 1'})],
            'Search Table',
        );
        expect(onSelectionChange.mock.lastCall?.[1][0]).not.toHaveProperty('__key');

        // Rows a running save submitted are on their way, not waiting.
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));
        expect(onSelectionChange).toHaveBeenLastCalledWith('table-1', [], 'Search Table');
        await act(async () => pending.resolve({tone: 'success', message: 'Saved.'}));
        expect(onSelectionChange).toHaveBeenLastCalledWith('table-1', [], 'Search Table');
    });

    it('starts over when its rows are reloaded, and a running save still reports here', async () => {
        const pending = deferred<SearchTableSaveResult>();
        const rows = [
            makeRow({id: 'p-1', team_number: 'T01', project_title: 'Project 1'}),
            makeRow({id: 'p-2', team_number: 'T02', project_title: 'Project 2'}),
        ];
        const props = {
            canRemove: true,
            tableId: 'table-1',
            title: 'Search Table',
            onRemove: vi.fn(),
            onMergeSelected: () => pending.promise,
        };
        const {container, rerender} = render(<SearchTableCard {...props} initialRows={rows} resetKey={0} />);
        fireEvent.change(within(cardSection(container)).getByRole('searchbox'), {target: {value: 'Project'}});
        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(rowCheckbox('Project 2'));
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));

        // A Refresh lands while the save runs: fresh rows, and the search starts over.
        const fresh = [...rows.map((row) => ({...row})), makeRow({id: 'p-3', team_number: 'T03', project_title: 'Project 3'})];
        rerender(<SearchTableCard {...props} initialRows={fresh} resetKey={1} />);
        expect(within(cardSection(container)).getByRole('searchbox')).toHaveValue('');
        expect(screen.getAllByText('Project 3').length).toBeGreaterThan(0);
        expect(screen.getByRole('button', {name: 'Adding…'})).toHaveAttribute('aria-disabled', 'true');

        await act(async () =>
            pending.resolve({
                tone: 'error',
                message: '1 project could not be loaded and is still selected.',
                retainedIndexes: [1],
            }),
        );
        expect(screen.getByRole('alert')).toHaveTextContent('1 project could not be loaded and is still selected.');
        // The failed project is checked again among the fresh rows.
        expect(rowCheckbox('Project 2')).toBeChecked();
        expect(rowCheckbox('Project 1')).not.toBeChecked();
    });

    it('says when a project to retry is not in the reloaded rows', async () => {
        const pending = deferred<SearchTableSaveResult>();
        const props = {
            canRemove: true,
            tableId: 'table-1',
            title: 'AI Search Table',
            onRemove: vi.fn(),
            onMergeSelected: () => pending.promise,
        };
        const {rerender} = render(
            <SearchTableCard {...props} initialRows={[makeRow({id: 'p-1', project_title: 'Old Result'})]} resetKey={1} />,
        );
        fireEvent.click(rowCheckbox('Old Result'));
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));
        rerender(<SearchTableCard {...props} initialRows={[makeRow({id: 'p-9', project_title: 'New Result'})]} resetKey={2} />);

        await act(async () => pending.resolve({tone: 'error', message: 'Could not load it.', retainedIndexes: [0]}));
        expect(screen.getByRole('alert')).toHaveTextContent('Could not load it. One of them is not in the reloaded table.');
        expect(rowCheckbox('New Result')).not.toBeChecked();
    });

    it('clears its selection and outcome when reloaded with no save running', () => {
        const props = {canRemove: true, tableId: 'table-1', title: 'Search Table', onRemove: vi.fn()};
        const onMergeSelected = vi.fn((): SearchTableSaveResult => ({tone: 'info', message: 'Already saved.'}));
        const {rerender} = render(
            <SearchTableCard {...props} initialRows={makeRows()} resetKey={0} onMergeSelected={onMergeSelected} />,
        );
        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));
        expect(screen.getByRole('status')).toHaveTextContent('Already saved.');
        fireEvent.click(rowCheckbox('Project 2'));

        rerender(<SearchTableCard {...props} initialRows={makeRows()} resetKey={1} onMergeSelected={onMergeSelected} />);
        expect(screen.getByRole('status')).toBeEmptyDOMElement();
        expect(rowCheckbox('Project 2')).not.toBeChecked();
        expect(screen.getByRole('button', {name: 'Add to Curation'})).toHaveAttribute('aria-disabled', 'true');
    });
});
