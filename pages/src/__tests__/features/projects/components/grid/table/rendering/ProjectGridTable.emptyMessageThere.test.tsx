import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/grid/table/ProjectGridTable';
import {baseProps} from '@/__tests__/features/projects/components/grid/table/rendering/projectGridTableFixtures';

describe('ProjectGridTable', () => {
    afterEach(() => {
        cleanup();
        vi.unstubAllGlobals();
    });

    it('shows an empty message when there are no paged rows', () => {
        render(
            <ProjectGridTable
                {...baseProps}
                rows={[]}
                pagedRows={[]}
                filteredCount={0}
                totalCount={0}
                emptyMessage="No merged results saved yet."
            />,
        );

        expect(screen.getAllByText('No merged results saved yet.').length).toBeGreaterThan(0);
    });

    it('renders the toolbar between the filter well and the results by default, or under them', () => {
        const toolbar = <button type="button">Export</button>;
        const {container, rerender} = render(<ProjectGridTable {...baseProps} toolbar={toolbar} />);

        const well = container.querySelector('.project-grid-controls');
        expect(well?.nextElementSibling?.className).toContain('project-grid-toolbar');
        expect(container.querySelector('.project-grid-toolbar + .project-grid-results-bar')).not.toBeNull();

        rerender(<ProjectGridTable {...baseProps} toolbar={toolbar} toolbarPlacement="bottom" />);
        const shell = container.querySelector('.project-grid-table-shell');
        expect(shell?.lastElementChild?.className).toContain('project-grid-toolbar--bottom');
    });

    it('renders extra filter fields in the filter well', () => {
        const {container} = render(
            <ProjectGridTable {...baseProps} filterControls={<label>Class<select aria-label="Class" /></label>} />,
        );

        expect(within(container.querySelector('.project-grid-controls') as HTMLElement).getByLabelText('Class')).toBeInTheDocument();
        expect(container.querySelector('.project-grid-controls-row')).toHaveClass('has-filters');
    });

    it('offers a Sort by select that moves Per page and View All Details into the results bar', () => {
        const onSortChange = vi.fn();
        const {container} = render(
            <ProjectGridTable
                {...baseProps}
                sortField="class_code"
                onSortChange={onSortChange}
                onToggleAllDetails={vi.fn()}
                sortOptions={[
                    {field: 'class_code', label: 'Team number'},
                    {field: 'project_title', label: 'Project title'},
                ]}
            />,
        );

        const resultsBar = within(container.querySelector('.project-grid-results-bar') as HTMLElement);
        const sortSelect = resultsBar.getByLabelText('Sort by');
        expect(sortSelect).toHaveValue('class_code:asc');
        expect(resultsBar.getByLabelText('Per page')).toBeInTheDocument();
        // The same outlined button as in the filter well of tables without a Sort select.
        expect(resultsBar.getByRole('button', {name: 'View All Details'})).toHaveClass('itg-btn-outline');

        // Without onSortSelect the select falls back to the header's toggle.
        fireEvent.change(sortSelect, {target: {value: 'project_title:asc'}});
        expect(onSortChange).toHaveBeenCalledWith('project_title');
    });

    it('offers each sort in both directions and shows the direction in use, since phones have no headers', () => {
        const onSortSelect = vi.fn();
        const onSortChange = vi.fn();
        render(
            <ProjectGridTable
                {...baseProps}
                sortField="project_title"
                sortDirection="desc"
                onSortChange={onSortChange}
                onSortSelect={onSortSelect}
                sortOptions={[
                    {field: 'class_code', label: 'Team number'},
                    {field: 'project_title', label: 'Project title'},
                ]}
            />,
        );

        const sortSelect = screen.getByLabelText('Sort by');
        expect(within(sortSelect).getAllByRole('option').map((option) => option.textContent)).toEqual([
            'Team number (low to high)',
            'Team number (high to low)',
            'Project title (A to Z)',
            'Project title (Z to A)',
        ]);
        expect(sortSelect).toHaveValue('project_title:desc');
        expect(within(sortSelect).getByRole('option', {name: 'Project title (Z to A)'})).toHaveProperty('selected', true);

        fireEvent.change(sortSelect, {target: {value: 'class_code:desc'}});
        expect(onSortSelect).toHaveBeenCalledWith('class_code', 'desc');
        expect(onSortChange).not.toHaveBeenCalled();
    });

    it('lists a column sorted from its header in the Sort by select', () => {
        render(
            <ProjectGridTable
                {...baseProps}
                sortField="industry"
                sortOptions={[{field: 'class_code', label: 'Team number'}]}
            />,
        );

        const sortSelect = screen.getByLabelText('Sort by');
        expect(sortSelect).toHaveValue('industry:asc');
        expect(within(sortSelect).getByRole('option', {name: 'Industry (A to Z)'})).toBeInTheDocument();
        expect(within(sortSelect).getByRole('option', {name: 'Industry (Z to A)'})).toBeInTheDocument();
    });

    it('shows a no-results state that clears the search and the filters', () => {
        const onSearchChange = vi.fn();
        const onClearFilters = vi.fn();
        const {container} = render(
            <ProjectGridTable
                {...baseProps}
                search="hydroponics"
                pagedRows={[]}
                filteredCount={0}
                totalCount={2}
                onSearchChange={onSearchChange}
                onClearFilters={onClearFilters}
                noResultsHint="Older projects are in Past Projects."
                noResultsActions={<a href="/past-projects">Search Past Projects</a>}
            />,
        );

        expect(screen.getByRole('heading', {level: 2, name: 'No projects match “hydroponics”'})).toBeInTheDocument();
        expect(screen.getByText(/Older projects are in Past Projects\./)).toBeInTheDocument();
        expect(screen.getByRole('link', {name: 'Search Past Projects'})).toBeInTheDocument();
        expect(container.querySelector('.project-grid-table-wrap')).toBeNull();

        fireEvent.click(screen.getByRole('button', {name: 'Clear Search'}));
        expect(onSearchChange).toHaveBeenCalledWith('');
        expect(onClearFilters).toHaveBeenCalledTimes(1);
    });

    it('names the filters in the no-results state, at the heading level the caller passes', () => {
        render(
            <ProjectGridTable
                {...baseProps}
                linkScope="past"
                pagedRows={[]}
                filteredCount={0}
                totalCount={2}
                noResultsHeadingLevel={4}
            />,
        );

        expect(screen.getByRole('heading', {level: 4, name: 'No projects match the filters'})).toBeInTheDocument();
    });

    it.each([2, 3, 4] as const)('renders the no-results heading as an h%i when asked to', (level) => {
        render(
            <ProjectGridTable
                {...baseProps}
                linkScope="past"
                search="zzz"
                pagedRows={[]}
                filteredCount={0}
                totalCount={2}
                noResultsHeadingLevel={level}
            />,
        );

        expect(screen.getByRole('heading', {name: 'No projects match “zzz”'}).tagName).toBe(`H${level}`);
    });
});
