import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/grid/table/ProjectGridTable';
import {createProjectGridItems} from '@/features/projects/components/grid/contracts/projectGrid';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';
import {baseProps, makeRow, makeRows} from '@/__tests__/features/projects/components/grid/table/rendering/projectGridTableFixtures';

describe('ProjectGridTable', () => {
    afterEach(() => {
        cleanup();
        vi.unstubAllGlobals();
    });

    it('expands a row through the desktop View button', () => {
        const rows = makeRows();
        const onToggleExpanded = vi.fn();
        render(
            <ProjectGridTable
                {...baseProps}
                rows={rows}
                pagedRows={rows}
                expandedKeys={new Set([rows[0].__key])}
                onToggleExpanded={onToggleExpanded}
            />,
        );

        // The desktop table's navy square button is named after its project; aria-expanded says whether it is open.
        const table = within(document.querySelector('.project-grid-table-wrap') as HTMLElement);
        const hide = table.getByRole('button', {name: 'Details for Project 1'});
        expect(hide).toHaveClass('project-grid-detail-icon-button');
        expect(hide).toHaveAttribute('aria-expanded', 'true');
        expect(hide.querySelector('.project-grid-detail-icon')).toHaveAttribute('aria-hidden', 'true');
        expect(table.getByRole('button', {name: 'Details for Project 2'})).toHaveAttribute('aria-expanded', 'false');
        fireEvent.click(hide);
        expect(onToggleExpanded).toHaveBeenCalledWith(rows[0].__key);
    });

    it('changes the page size through the Per page select', () => {
        const onPageSizeChange = vi.fn();
        render(<ProjectGridTable {...baseProps} onPageSizeChange={onPageSizeChange} />);

        const select = screen.getByLabelText('Per page');
        expect(select).toHaveValue('5');
        expect(within(select).getAllByRole('option').map((option) => option.textContent)).toEqual(['5', '10', '25']);

        fireEvent.change(select, {target: {value: '25'}});
        expect(onPageSizeChange).toHaveBeenCalledWith(25);
    });

    it('marks saved and newly added rows with tags after the title', () => {
        const rows = makeRows();
        const {container} = render(
            <ProjectGridTable
                {...baseProps}
                rows={rows}
                pagedRows={rows}
                isRowSaved={(row) => row.__key === rows[0].__key}
                highlightedKeys={new Set([rows[1].__key])}
            />,
        );

        const table = within(container.querySelector('.project-grid-table-wrap') as HTMLElement);
        expect(table.getByText('Saved')).toHaveClass('itg-tag', 'itg-tag-saved');
        expect(table.getByText('New')).toHaveClass('itg-tag', 'itg-tag-new');
        expect(table.getByText('Project 1').closest('tr')).toHaveClass('is-saved');
        expect(table.getByText('Project 2').closest('tr')).toHaveClass('is-new');
    });

    it('links past-project titles to their page in a new tab', () => {
        const rows = createProjectGridItems([makeRow({id: 'p-1'})], 'linked');
        const {container} = render(
            <ProjectGridTable {...baseProps} linkScope="past" rows={rows} pagedRows={rows} filteredCount={1} totalCount={1} />,
        );

        const link = within(container.querySelector('.project-grid-table-wrap') as HTMLElement).getByRole('link', {
            name: /Alpha Project/,
        });
        expect(link).toHaveAttribute('href', `${window.location.origin}/past-projects/project/p-1`);
        expect(link).toHaveAttribute('target', '_blank');
        expect(link).toHaveTextContent('(opens in a new tab)');
    });

    it('shows a phone list with the term, team code and industry above each title', () => {
        stubGridLayout('phone');
        const rows = createProjectGridItems([makeRow({team_number: '7'})], 'phone');
        const {container} = render(
            <ProjectGridTable
                {...baseProps}
                rows={rows}
                pagedRows={rows}
                filteredCount={1}
                totalCount={1}
                selectable
                selectedKeys={new Set([rows[0].__key])}
                onToggleSelected={vi.fn()}
            />,
        );

        const card = container.querySelector('.project-grid-mobile-card') as HTMLElement;
        expect(card).toHaveClass('is-selected');
        expect(within(card).getByText('2025 Spring · ENGR 120 7 · Technology')).toBeInTheDocument();
        expect(within(card).getByText('Team Alpha · Acme')).toBeInTheDocument();
        expect(within(card).getByRole('checkbox', {name: 'Select Alpha Project'})).toBeChecked();
        fireEvent.click(within(card).getByRole('button', {name: 'Show Details for Alpha Project'}));
        expect(baseProps.onToggleExpanded).toHaveBeenCalledWith(rows[0].__key);
    });
});
