import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SearchTableCard} from '@/features/projects/components/search/cards/SearchTableCard';
import {cardSection, makeRows, rowCheckbox} from '@/__tests__/features/projects/components/search/cards/card/searchTableCardFixtures';

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

    it('removes the checked rows from the table and lets the user undo the last change', () => {
        renderCard();

        const undoButton = screen.getByRole('button', {name: 'Undo Row Change'});
        expect(undoButton).toHaveAttribute('aria-disabled', 'true');

        fireEvent.click(rowCheckbox('Project 2'));
        fireEvent.click(screen.getByRole('button', {name: 'Remove from Table'}));

        expect(screen.queryByText('Project 2')).toBeNull();
        expect(undoButton).not.toHaveAttribute('aria-disabled');

        fireEvent.click(undoButton);
        expect(screen.getAllByText('Project 2').length).toBeGreaterThan(0);
    });

    it('keeps only the checked rows, keeps them checked for Save, and undoes that change', () => {
        renderCard();

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(screen.getByRole('button', {name: 'Keep Only Selected'}));

        // Only the checked row remains, still checked so Add to Curation works right away.
        expect(screen.getAllByText('Project 1').length).toBeGreaterThan(0);
        expect(screen.queryByText('Project 2')).toBeNull();
        expect(screen.queryByText('Project 3')).toBeNull();
        expect(rowCheckbox('Project 1')).toBeChecked();
        expect(screen.getByRole('button', {name: 'Add to Curation'})).not.toHaveAttribute('aria-disabled');

        fireEvent.click(screen.getByRole('button', {name: 'Undo Row Change'}));
        expect(screen.getAllByText('Project 3').length).toBeGreaterThan(0);
    });

    it('leaves the table and selection alone when every row is already shown', () => {
        renderCard();

        fireEvent.click(screen.getByRole('button', {name: 'Select All'}));
        fireEvent.click(screen.getByRole('button', {name: 'Keep Only Selected'}));

        expect(screen.getAllByText('Project 3').length).toBeGreaterThan(0);
        expect(rowCheckbox('Project 3')).toBeChecked();
        expect(screen.getByRole('button', {name: 'Undo Row Change'})).toHaveAttribute('aria-disabled', 'true');
    });

    it('selects all rows and then deselects them', () => {
        renderCard();

        const saveButton = screen.getByRole('button', {name: 'Add to Curation'});
        expect(saveButton).toHaveAttribute('aria-disabled', 'true');

        fireEvent.click(screen.getByRole('button', {name: 'Select All'}));
        expect(saveButton).not.toHaveAttribute('aria-disabled');
        expect(screen.getByText('3 selected')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Deselect'}));
        expect(saveButton).toHaveAttribute('aria-disabled', 'true');
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
});
