import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SearchTableCard} from '@/features/projects/components/SearchTableCard';
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

describe('SearchTableCard', () => {
    afterEach(() => {
        cleanup();
    });

    it('renders the title, description, and per-table entry counts', () => {
        renderCard();

        expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
        expect(screen.getByText(/filter this table, select rows/i)).toBeInTheDocument();
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
        const onMergeSelected = vi.fn().mockResolvedValue(true);
        renderCard({onMergeSelected});

        fireEvent.click(screen.getAllByLabelText('Select Project 2')[0]);
        const mergeButton = screen.getByRole('button', {name: 'Save Selected'});
        expect(mergeButton).toBeEnabled();

        fireEvent.click(mergeButton);

        await waitFor(() => expect(onMergeSelected).toHaveBeenCalledTimes(1));
        const [rowsArg] = onMergeSelected.mock.calls[0];
        expect(rowsArg).toHaveLength(1);
        expect(rowsArg[0]).toMatchObject({project_title: 'Project 2'});
        expect(rowsArg[0]).not.toHaveProperty('__key');

        await waitFor(() => expect(mergeButton).toBeDisabled());
    });

    it('keeps the selection when the merge fails with false', async () => {
        const onMergeSelected = vi.fn().mockResolvedValue(false);
        renderCard({onMergeSelected});

        fireEvent.click(screen.getAllByLabelText('Select Project 2')[0]);
        fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));

        await waitFor(() => expect(onMergeSelected).toHaveBeenCalledTimes(1));
        // The selection is preserved so the user can retry without re-checking.
        expect(screen.getAllByLabelText('Select Project 2')[0]).toBeChecked();
    });

    it('deletes selected rows and lets the user undo the last change', () => {
        renderCard();

        const undoButton = screen.getByRole('button', {name: 'Undo Row Change'});
        expect(undoButton).toBeDisabled();

        fireEvent.click(screen.getAllByLabelText('Select Project 2')[0]);
        fireEvent.click(screen.getByRole('button', {name: 'Delete Selected'}));

        expect(screen.queryByText('Project 2')).toBeNull();
        expect(undoButton).toBeEnabled();

        fireEvent.click(undoButton);
        expect(screen.getAllByText('Project 2').length).toBeGreaterThan(0);
    });

    it('keeps only the selected rows and undoes that change', () => {
        renderCard();

        fireEvent.click(screen.getAllByLabelText('Select Project 1')[0]);
        fireEvent.click(screen.getByRole('button', {name: 'Keep Selected'}));

        // Only the checked row remains.
        expect(screen.getAllByText('Project 1').length).toBeGreaterThan(0);
        expect(screen.queryByText('Project 2')).toBeNull();
        expect(screen.queryByText('Project 3')).toBeNull();

        fireEvent.click(screen.getByRole('button', {name: 'Undo Row Change'}));
        expect(screen.getAllByText('Project 3').length).toBeGreaterThan(0);
    });

    it('clears the selection without removing rows when every row is kept', () => {
        renderCard();

        fireEvent.click(screen.getByRole('button', {name: 'Select All Entries'}));
        fireEvent.click(screen.getByRole('button', {name: 'Keep Selected'}));

        // All rows remain, but the selection is cleared.
        expect(screen.getAllByText('Project 3').length).toBeGreaterThan(0);
        expect(screen.getByRole('button', {name: 'Keep Selected'})).toBeDisabled();
    });

    it('selects all entries and then deselects them', () => {
        renderCard();

        const saveButton = screen.getByRole('button', {name: 'Save Selected'});
        expect(saveButton).toBeDisabled();

        fireEvent.click(screen.getByRole('button', {name: 'Select All Entries'}));
        expect(saveButton).toBeEnabled();

        fireEvent.click(screen.getByRole('button', {name: 'Deselect'}));
        expect(saveButton).toBeDisabled();
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

    it('disables the merge button when mergeDisabled is set', () => {
        renderCard({mergeDisabled: true});

        fireEvent.click(screen.getAllByLabelText('Select Project 1')[0]);
        expect(screen.getByRole('button', {name: 'Save Selected'})).toBeDisabled();
    });

    it('uses a custom merge label', () => {
        renderCard({mergeLabel: 'Add Selected'});

        expect(screen.getByRole('button', {name: 'Add Selected'})).toBeInTheDocument();
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
