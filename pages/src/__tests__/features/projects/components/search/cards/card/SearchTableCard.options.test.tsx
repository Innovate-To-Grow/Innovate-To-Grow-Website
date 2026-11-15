import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SearchTableCard, type SearchTableSaveResult} from '@/features/projects/components/search/cards/SearchTableCard';
import {cardSection, deferred, makeRows, rowCheckbox} from '@/__tests__/features/projects/components/search/cards/card/searchTableCardFixtures';

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

    it('marks rows that are already saved', () => {
        renderCard({isRowSaved: (row) => row.project_title === 'Project 2', savedRowLabel: 'Saved'});

        // The table marks it, and the title stays findable by its own text.
        expect(screen.getAllByText('Saved')).toHaveLength(1);
        expect(screen.getAllByText('Project 2')).toHaveLength(1);
    });

    it('disables the merge button when mergeDisabled is set', () => {
        renderCard({mergeDisabled: true});

        fireEvent.click(rowCheckbox('Project 1'));
        expect(screen.getByRole('button', {name: 'Add to Curation'})).toHaveAttribute('aria-disabled', 'true');
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
