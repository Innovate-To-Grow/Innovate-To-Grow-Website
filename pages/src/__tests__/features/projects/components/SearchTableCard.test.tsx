import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SearchTableCard, type SearchTableSaveHelpers, type SearchTableSaveResult} from '@/features/projects/components/SearchTableCard';
import type {ProjectGridRow} from '@/features/projects/components/projectGrid';

const makeRow = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
    semester_label: '2025-1 Spring',
    class_code: 'ENGR 120',
    team_number: 'T01',
    team_name: 'Team Alpha',
    project_title: 'Alpha Project',
    organization: 'Acme',
    industry: 'Technology',
    abstract: 'An abstract',
    student_names: 'Alice',
    is_presenting: '',
    ...overrides,
});

const makeRows = (count = 3): ProjectGridRow[] =>
    Array.from({length: count}, (_, index) =>
        makeRow({
            team_number: `T0${index + 1}`,
            team_name: `Team ${index + 1}`,
            project_title: `Project ${index + 1}`,
        }),
    );

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

const cardSection = (container: HTMLElement) =>
    container.querySelector('.search-table-card') as HTMLElement;

const rowCheckbox = (title: string) => screen.getAllByLabelText(`Select ${title}`)[0];

const deferred = <T,>() => {
    let resolve!: (value: T) => void;
    let reject!: (reason: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return {promise, resolve, reject};
};

describe('SearchTableCard', () => {
    afterEach(() => {
        cleanup();
    });

    it('renders the title, description, and per-table entry counts', () => {
        renderCard();

        expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
        expect(screen.getByText(/check the projects you want, then click save selected/i)).toBeInTheDocument();
        expect(screen.getByText('entries')).toBeInTheDocument();
    });

    it('hides the remove button when the table cannot be removed', () => {
        renderCard({canRemove: false});

        expect(screen.queryByRole('button', {name: /delete search table/i})).toBeNull();
    });

    it('forwards removal of the table via its id', () => {
        const onRemove = vi.fn();
        renderCard({onRemove});

        fireEvent.click(screen.getByRole('button', {name: 'Delete Search Table'}));
        expect(onRemove).toHaveBeenCalledWith('table-1');
    });

    it('saves the checked rows and clears the selection on success', async () => {
        const onMergeSelected = vi.fn().mockResolvedValue({tone: 'success', message: '1 project added.'});
        renderCard({onMergeSelected});

        fireEvent.click(rowCheckbox('Project 2'));
        const mergeButton = screen.getByRole('button', {name: 'Save Selected'});
        expect(mergeButton).toBeEnabled();

        fireEvent.click(mergeButton);

        await waitFor(() => expect(onMergeSelected).toHaveBeenCalledTimes(1));
        const [rowsArg] = onMergeSelected.mock.calls[0];
        expect(rowsArg).toHaveLength(1);
        expect(rowsArg[0]).toMatchObject({project_title: 'Project 2'});
        expect(rowsArg[0]).not.toHaveProperty('__key');

        await waitFor(() => expect(screen.getByRole('button', {name: 'Save Selected'})).toBeDisabled());
        expect(rowCheckbox('Project 2')).not.toBeChecked();
    });

    it('reports a synchronous save inside the table straight away', () => {
        const onMergeSelected = vi.fn(
            (): SearchTableSaveResult => ({tone: 'info', message: 'That project is already in Saved Merged Results.'}),
        );
        renderCard({onMergeSelected});

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));

        expect(screen.getByRole('status')).toHaveTextContent('That project is already in Saved Merged Results.');
        expect(rowCheckbox('Project 1')).not.toBeChecked();
        expect(screen.getByRole('button', {name: 'Save Selected'})).toBeDisabled();
    });

    it('keeps only the retained rows checked and shows the error beside the toolbar', async () => {
        const onMergeSelected = vi.fn().mockResolvedValue({
            tone: 'error',
            message: '1 project could not be loaded and is still selected. Click Save Selected to try again.',
            retainedIndexes: [1],
        } satisfies SearchTableSaveResult);
        renderCard({onMergeSelected});

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(rowCheckbox('Project 3'));
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));

        await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('1 project could not be loaded'));
        expect(screen.getByText(/^1 project could not be loaded/, {selector: 'span'})).toBeVisible();
        // Rows are submitted in table order; index 1 is Project 3.
        expect(rowCheckbox('Project 1')).not.toBeChecked();
        expect(rowCheckbox('Project 3')).toBeChecked();
    });

    it('keeps the whole selection and explains when the save rejects', async () => {
        renderCard({onMergeSelected: vi.fn().mockRejectedValue(new Error('boom'))});

        fireEvent.click(rowCheckbox('Project 2'));
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));

        await waitFor(() =>
            expect(screen.getByRole('alert')).toHaveTextContent('Could not save the selected projects.'),
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
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));

        expect(helpers?.tableId).toBe('table-1');
        // aria-disabled rather than disabled, so keyboard focus stays on the pressed button.
        const savingButton = screen.getByRole('button', {name: 'Saving…'});
        expect(savingButton).toHaveAttribute('aria-disabled', 'true');
        expect(savingButton).toBeEnabled();
        expect(screen.getByRole('status')).toHaveTextContent('Saving 2 projects…');
        // Progress shows for larger loads only, in steps, and stays out of the live region. It counts settled
        // requests, so it is worded as progress rather than as a number of loaded projects.
        act(() => helpers?.reportProgress(8, 40));
        expect(screen.getByText(/Loading details: 8 of 40\./)).toBeInTheDocument();
        expect(screen.getByRole('status')).not.toHaveTextContent('Loading details');
        // Tidying the table while it saves would contradict the outcome it is about to report.
        expect(screen.getByRole('button', {name: 'Remove from Table'})).toBeDisabled();
        expect(screen.getByRole('button', {name: 'Delete Search Table'})).toBeDisabled();

        // Checked while the save is running: must survive the save finishing.
        fireEvent.click(rowCheckbox('Project 3'));
        fireEvent.click(savingButton);
        expect(onMergeSelected).toHaveBeenCalledTimes(1);

        await act(async () => {
            pending.resolve({tone: 'success', message: '2 projects added to Saved Merged Results (2 in total).'});
        });

        expect(screen.getByRole('status')).toHaveTextContent('2 projects added to Saved Merged Results');
        expect(screen.getByRole('button', {name: 'Save Selected'})).not.toHaveAttribute('aria-disabled');
        expect(rowCheckbox('Project 1')).not.toBeChecked();
        expect(rowCheckbox('Project 2')).not.toBeChecked();
        expect(rowCheckbox('Project 3')).toBeChecked();

        fireEvent.click(screen.getByRole('button', {name: 'View Saved Results'}));
        expect(onViewMergedResults).toHaveBeenCalledTimes(1);
    });

    it('keeps every submitted row checked when an error result names no retained rows', async () => {
        renderCard({onMergeSelected: vi.fn().mockResolvedValue({tone: 'error', message: 'Boom'})});

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(rowCheckbox('Project 2'));
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));

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
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));
        const dialog = screen.getByRole('dialog', {name: 'Save 120 projects?'});
        expect(onMergeSelected).not.toHaveBeenCalled();

        fireEvent.click(within(dialog).getByRole('button', {name: 'Cancel'}));
        expect(onMergeSelected).not.toHaveBeenCalled();
        expect(rowCheckbox('Bulk 0')).toBeChecked();

        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));
        fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Save 120 Projects'}));
        await waitFor(() => expect(onMergeSelected).toHaveBeenCalledTimes(1));
        expect(onMergeSelected.mock.calls[0][0]).toHaveLength(120);
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
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));
        const dialog = screen.getByRole('dialog', {name: 'Save 120 projects?'});
        expect(within(dialog).getByRole('button', {name: 'Save 120 Projects'})).toHaveFocus();

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

        fireEvent.click(screen.getByRole('button', {name: /per page/i}));
        fireEvent.click(screen.getByRole('option', {name: '25'}));
        const bottom = container.querySelector('.search-table-bottom-actions') as HTMLElement;
        expect(bottom).not.toBeNull();

        fireEvent.click(rowCheckbox('Row 3'));
        expect(within(bottom).getByText('1 selected')).toBeInTheDocument();
        fireEvent.click(within(bottom).getByRole('button', {name: 'Save Selected'}));

        expect(within(bottom).getByText('Saved from below.')).toBeInTheDocument();
        expect(container.querySelector('.project-grid-toolbar .search-table-save-status')).toBeNull();
    });

    it('moves the outcome to the top Save button once the bottom one is gone', async () => {
        const pending = deferred<SearchTableSaveResult>();
        const rows = Array.from({length: 12}, (_, index) => makeRow({team_number: `T${index}`, project_title: `Row ${index}`}));
        const {container} = renderCard({initialRows: rows, onMergeSelected: () => pending.promise});
        fireEvent.click(screen.getByRole('button', {name: /per page/i}));
        fireEvent.click(screen.getByRole('option', {name: '25'}));
        fireEvent.click(rowCheckbox('Row 3'));
        const bottom = container.querySelector('.search-table-bottom-actions') as HTMLElement;
        fireEvent.click(within(bottom).getByRole('button', {name: 'Save Selected'}));

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
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));
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
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));

        // A Refresh lands while the save runs: fresh rows, and the search starts over.
        const fresh = [...rows.map((row) => ({...row})), makeRow({id: 'p-3', team_number: 'T03', project_title: 'Project 3'})];
        rerender(<SearchTableCard {...props} initialRows={fresh} resetKey={1} />);
        expect(within(cardSection(container)).getByRole('searchbox')).toHaveValue('');
        expect(screen.getAllByText('Project 3').length).toBeGreaterThan(0);
        expect(screen.getByRole('button', {name: 'Saving…'})).toHaveAttribute('aria-disabled', 'true');

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
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));
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
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));
        expect(screen.getByRole('status')).toHaveTextContent('Already saved.');
        fireEvent.click(rowCheckbox('Project 2'));

        rerender(<SearchTableCard {...props} initialRows={makeRows()} resetKey={1} onMergeSelected={onMergeSelected} />);
        expect(screen.getByRole('status')).toBeEmptyDOMElement();
        expect(rowCheckbox('Project 2')).not.toBeChecked();
        expect(screen.getByRole('button', {name: 'Save Selected'})).toBeDisabled();
    });

    it('removes the checked rows from the table and lets the user undo the last change', () => {
        renderCard();

        const undoButton = screen.getByRole('button', {name: 'Undo Row Change'});
        expect(undoButton).toBeDisabled();

        fireEvent.click(rowCheckbox('Project 2'));
        fireEvent.click(screen.getByRole('button', {name: 'Remove from Table'}));

        expect(screen.queryByText('Project 2')).toBeNull();
        expect(undoButton).toBeEnabled();

        fireEvent.click(undoButton);
        expect(screen.getAllByText('Project 2').length).toBeGreaterThan(0);
    });

    it('keeps only the checked rows, keeps them checked for Save, and undoes that change', () => {
        renderCard();

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(screen.getByRole('button', {name: 'Keep Only Selected'}));

        // Only the checked row remains, still checked so Save Selected works right away.
        expect(screen.getAllByText('Project 1').length).toBeGreaterThan(0);
        expect(screen.queryByText('Project 2')).toBeNull();
        expect(screen.queryByText('Project 3')).toBeNull();
        expect(rowCheckbox('Project 1')).toBeChecked();
        expect(screen.getByRole('button', {name: 'Save Selected'})).toBeEnabled();

        fireEvent.click(screen.getByRole('button', {name: 'Undo Row Change'}));
        expect(screen.getAllByText('Project 3').length).toBeGreaterThan(0);
    });

    it('leaves the table and selection alone when every row is already shown', () => {
        renderCard();

        fireEvent.click(screen.getByRole('button', {name: 'Select All'}));
        fireEvent.click(screen.getByRole('button', {name: 'Keep Only Selected'}));

        expect(screen.getAllByText('Project 3').length).toBeGreaterThan(0);
        expect(rowCheckbox('Project 3')).toBeChecked();
        expect(screen.getByRole('button', {name: 'Undo Row Change'})).toBeDisabled();
    });

    it('selects all rows and then deselects them', () => {
        renderCard();

        const saveButton = screen.getByRole('button', {name: 'Save Selected'});
        expect(saveButton).toBeDisabled();

        fireEvent.click(screen.getByRole('button', {name: 'Select All'}));
        expect(saveButton).toBeEnabled();
        expect(screen.getByText('3 selected')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Deselect'}));
        expect(saveButton).toBeDisabled();
        expect(screen.queryByText(/selected$/)).toBeNull();
    });

    it('toggles all rows through the header select-all checkbox', () => {
        const {container} = renderCard();
        const table = cardSection(container);

        const selectAll = within(table).getByRole('checkbox', {name: 'Select all rows'});
        fireEvent.click(selectAll);
        expect(within(table).getAllByRole('checkbox', {name: 'Select Project 1'})[0]).toBeChecked();

        fireEvent.click(selectAll);
        expect(within(table).getAllByRole('checkbox', {name: 'Select Project 1'})[0]).not.toBeChecked();
    });

    it('selects only the rows the current search shows from the header checkbox', async () => {
        const {container} = renderCard();
        const table = cardSection(container);

        // Regression: with a search active, the header checkbox used to select every row in the table,
        // so "select all, then uncheck a few" saved hundreds of hidden archive projects.
        fireEvent.change(within(table).getByRole('searchbox'), {target: {value: 'Project 2'}});
        await waitFor(() => expect(screen.queryByText('Project 1')).toBeNull());
        fireEvent.click(within(table).getByRole('checkbox', {name: 'Select all rows'}));
        expect(screen.getByText('1 selected')).toBeInTheDocument();

        fireEvent.change(within(table).getByRole('searchbox'), {target: {value: ''}});
        await waitFor(() => expect(screen.getAllByText('Project 1').length).toBeGreaterThan(0));
        expect(rowCheckbox('Project 1')).not.toBeChecked();
        expect(rowCheckbox('Project 2')).toBeChecked();
    });

    it('adds the matching rows to an earlier selection and counts rows the search hides', async () => {
        const {container} = renderCard();
        const table = cardSection(container);

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.change(within(table).getByRole('searchbox'), {target: {value: 'Project 3'}});
        await waitFor(() => expect(screen.queryByText('Project 2')).toBeNull());
        fireEvent.click(screen.getByRole('button', {name: 'Select All'}));

        expect(screen.getByText('2 selected (1 not shown by the current search)')).toBeInTheDocument();
        // The header checkbox only clears what the search shows.
        fireEvent.click(within(table).getByRole('checkbox', {name: 'Select all rows'}));
        expect(screen.getByText('1 selected (1 not shown by the current search)')).toBeInTheDocument();
    });

    it('marks rows that are already saved', () => {
        renderCard({isRowSaved: (row) => row.project_title === 'Project 2', savedRowLabel: 'Saved'});

        // The desktop table and the mobile cards each mark it, and the title stays findable by its own text.
        expect(screen.getAllByText('Saved')).toHaveLength(2);
        expect(screen.getAllByText('Project 2')).toHaveLength(2);
    });

    it('disables the merge button when mergeDisabled is set', () => {
        renderCard({mergeDisabled: true});

        fireEvent.click(rowCheckbox('Project 1'));
        expect(screen.getByRole('button', {name: 'Save Selected'})).toBeDisabled();
    });

    it('uses a custom merge label and in-flight verb', async () => {
        const pending = deferred<SearchTableSaveResult>();
        renderCard({mergeLabel: 'Add Selected', mergingVerb: 'Adding', onMergeSelected: () => pending.promise});

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(screen.getByRole('button', {name: 'Add Selected'}));

        expect(screen.getByRole('button', {name: 'Adding…'})).toHaveAttribute('aria-disabled', 'true');
        expect(screen.getByRole('status')).toHaveTextContent('Adding 1 project…');
        await act(async () => pending.resolve({tone: 'success', message: '1 project added.'}));
    });

    it('shows a refresh button and forwards it to onRefresh', () => {
        const onRefresh = vi.fn();
        renderCard({onRefresh});

        fireEvent.click(screen.getByRole('button', {name: 'Refresh Search Table'}));
        expect(onRefresh).toHaveBeenCalledWith('table-1');
    });

    it('omits the refresh button when no onRefresh is provided', () => {
        renderCard({onRefresh: undefined});

        expect(screen.queryByRole('button', {name: 'Refresh Search Table'})).toBeNull();
    });

    it('renders a custom search control and controls status', () => {
        renderCard({
            searchControl: <input aria-label="Custom AI search" />,
            controlsStatus: <span>Loading...</span>,
        });

        expect(screen.getByLabelText('Custom AI search')).toBeInTheDocument();
        expect(screen.queryByRole('searchbox')).toBeNull();
        expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('shows an empty message when there are no initial rows', () => {
        renderCard({initialRows: [], emptyMessage: 'Run AI search to load projects into this table.'});

        expect(screen.getAllByText('Run AI search to load projects into this table.').length).toBeGreaterThan(0);
    });

    it('applies the className and results motion key', () => {
        const {container} = renderCard({className: 'is-ai-search-table', resultsMotionKey: 3});

        expect(cardSection(container)).toHaveClass('is-ai-search-table');
        expect(container.querySelector('.search-table-results-motion')).not.toBeNull();
    });
});
