import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
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

    it('renders the title, description, and the project count of the table', () => {
        renderCard();

        expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
        expect(screen.getByText(/check the projects you want, then click add to curation/i)).toBeInTheDocument();
        expect(screen.getByText('3 projects')).toBeInTheDocument();
    });

    it('heads a search with no matches one level under the card title (h4)', () => {
        const {container} = renderCard();

        fireEvent.change(within(cardSection(container)).getByRole('searchbox'), {target: {value: 'hydroponics'}});

        expect(screen.getByRole('heading', {level: 4, name: 'No projects match “hydroponics”'})).toBeInTheDocument();
    });

    it('groups the actions: Save, then Selection, then Tidy this table, as text buttons', () => {
        const {container} = renderCard({onRefresh: vi.fn()});
        const toolbar = container.querySelector('.project-grid-toolbar') as HTMLElement;

        expect(within(toolbar).getByRole('button', {name: 'Add to Curation'})).toHaveClass('itg-btn-primary');
        const selection = within(toolbar).getByRole('group', {name: 'Selection'});
        expect(within(selection).getAllByRole('button').map((button) => button.textContent)).toEqual([
            'Select All',
            'Deselect',
        ]);
        const tidy = within(toolbar).getByRole('group', {name: 'Tidy this table'});
        expect(within(tidy).getAllByRole('button').map((button) => button.textContent)).toEqual([
            'Remove from Table',
            'Keep Only Selected',
            'Undo Row Change',
            'Refresh Search Table',
        ]);
        within(tidy).getAllByRole('button').forEach((button) => expect(button).toHaveClass('itg-btn-text'));
    });

    it('folds the table-tidying buttons into "More Table Actions" on phones', () => {
        vi.stubGlobal('matchMedia', (query: string) => ({
            matches: query === '(max-width: 768px)',
            media: query,
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
        }));
        const {container} = renderCard({onRefresh: vi.fn()});
        const toolbar = container.querySelector('.project-grid-toolbar') as HTMLElement;

        const more = within(toolbar).getByText('More Table Actions').closest('details') as HTMLElement;
        expect(more).not.toHaveAttribute('open');
        expect(within(more).getByRole('group', {name: 'Tidy this table'})).toBeInTheDocument();
        // Save and the selection buttons stay in view.
        expect(within(toolbar).getByRole('button', {name: 'Add to Curation'})).toBeVisible();
        expect(within(toolbar).getByRole('group', {name: 'Selection'}).closest('details')).toBeNull();
        vi.unstubAllGlobals();
    });

    it('counts the checked rows in the Save button for phones without changing its name', () => {
        renderCard();

        fireEvent.click(rowCheckbox('Project 1'));
        fireEvent.click(rowCheckbox('Project 2'));

        const save = screen.getByRole('button', {name: 'Add to Curation'});
        expect(save).toHaveTextContent('Add to Curation · 2');
        expect(within(save).getByText('· 2', {exact: false})).toHaveAttribute('aria-hidden', 'true');
    });

    it('hides the remove button when the table cannot be removed', () => {
        renderCard({canRemove: false});

        expect(screen.queryByRole('button', {name: /delete table/i})).toBeNull();
    });

    it('forwards removal of the table via its id', () => {
        const onRemove = vi.fn();
        renderCard({onRemove});

        fireEvent.click(screen.getByRole('button', {name: 'Delete Table: Search Table'}));
        expect(onRemove).toHaveBeenCalledWith('table-1');
    });
});
