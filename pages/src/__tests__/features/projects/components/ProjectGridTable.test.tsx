import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/ProjectGridTable';
import {getPagerItems} from '@/features/projects/components/grid/pagerItems';
import {
    PAST_PROJECT_GRID_COLUMNS,
    createProjectGridItems,
    type ProjectGridColumnKey,
    type ProjectGridItem,
    type ProjectGridRow,
    type ProjectGridSortDirection,
} from '@/features/projects/components/projectGrid';

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

const makeRows = (count = 2): ProjectGridItem[] =>
    createProjectGridItems(
        Array.from({length: count}, (_, index) =>
            makeRow({
                team_number: `T0${index + 1}`,
                team_name: `Team ${index + 1}`,
                project_title: `Project ${index + 1}`,
            }),
        ),
        'test',
    );

const baseProps = {
    columns: PAST_PROJECT_GRID_COLUMNS,
    rows: makeRows(),
    pagedRows: makeRows(),
    filteredCount: 2,
    totalCount: 2,
    search: '',
    sortField: 'semester_label' as ProjectGridColumnKey,
    sortDirection: 'asc' as ProjectGridSortDirection,
    onSearchChange: vi.fn(),
    onSortChange: vi.fn(),
    expandedKeys: new Set<string>(),
    onToggleExpanded: vi.fn(),
    page: 0,
    totalPages: 1,
    onPageChange: vi.fn(),
    pageSize: 5,
    pageSizeOptions: [5, 10, 25],
    onPageSizeChange: vi.fn(),
};

describe('ProjectGridTable', () => {
    afterEach(() => {
        cleanup();
    });

    it('renders a labelled search field and reports the row count and the rows shown', () => {
        const {container} = render(<ProjectGridTable {...baseProps} />);

        expect(screen.getByLabelText('Search')).toHaveAttribute('placeholder', 'Search projects...');
        expect(screen.getByText('2 projects')).toBeInTheDocument();
        expect(container.querySelector('.project-grid-count')).toHaveTextContent('2 projects · showing 1–2');
    });

    it('uses a custom search label, placeholder and count label', () => {
        render(
            <ProjectGridTable
                {...baseProps}
                searchLabel="Search this list"
                searchPlaceholder="Find entries..."
                countLabel="teams"
            />,
        );

        expect(screen.getByLabelText('Search this list')).toHaveAttribute('placeholder', 'Find entries...');
        expect(screen.getByText('2 teams')).toBeInTheDocument();
    });

    it('counts a single row in the singular', () => {
        const rows = makeRows(1);
        render(<ProjectGridTable {...baseProps} rows={rows} pagedRows={rows} filteredCount={1} totalCount={1} />);

        expect(screen.getByText('1 project')).toBeInTheDocument();
    });

    it('says how many rows match the search', () => {
        const rows = makeRows(1);
        const {container} = render(
            <ProjectGridTable {...baseProps} search="water" pagedRows={rows} filteredCount={1} totalCount={2} />,
        );

        expect(container.querySelector('.project-grid-count')).toHaveTextContent(
            '1 of 2 projects matches “water” · showing 1–1',
        );
    });

    it('forwards search changes to onSearchChange', () => {
        const onSearchChange = vi.fn();
        render(<ProjectGridTable {...baseProps} onSearchChange={onSearchChange} />);

        fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'solar'}});
        expect(onSearchChange).toHaveBeenCalledWith('solar');
    });

    it('forwards column sort clicks to onSortChange', () => {
        const onSortChange = vi.fn();
        const {container} = render(<ProjectGridTable {...baseProps} onSortChange={onSortChange} />);

        const table = container.querySelector('.project-grid-table-wrap') as HTMLElement;
        const titleHeader = within(table).getByRole('columnheader', {name: 'Project'});
        fireEvent.click(within(titleHeader).getByRole('button'));
        expect(onSortChange).toHaveBeenCalledWith('project_title');
    });

    it('marks the sorted header and shades the sorted column, DataTables style', () => {
        const {container} = render(
            <ProjectGridTable {...baseProps} sortField="organization" sortDirection="desc" />,
        );

        const table = within(container.querySelector('.project-grid-table-wrap') as HTMLElement);
        const organizationHeader = table.getByRole('columnheader', {name: 'Organization'});
        expect(organizationHeader).toHaveAttribute('aria-sort', 'descending');
        expect(organizationHeader).toHaveClass('project-grid-sortable', 'is-sorted', 'is-sorted-desc');
        const projectHeader = table.getByRole('columnheader', {name: 'Project'});
        expect(projectHeader).toHaveClass('project-grid-sortable');
        expect(projectHeader).not.toHaveClass('is-sorted');
        // The arrows are drawn by CSS: the header button holds the label only.
        expect(within(organizationHeader).getByRole('button')).toHaveTextContent(/^Organization$/);

        const sortedCells = container.querySelectorAll('tbody td.is-sorted-col');
        expect(sortedCells).toHaveLength(2);
        sortedCells.forEach((cell) => expect(cell).toHaveClass('project-grid-col-organization'));
        // The details column is headed "Details", as on the reference table.
        expect(table.getByRole('columnheader', {name: 'Details'})).toBeInTheDocument();
    });

    it('renders the loading state instead of the table', () => {
        const {container} = render(<ProjectGridTable {...baseProps} loading />);

        expect(screen.getByText('Loading project data...')).toBeInTheDocument();
        expect(container.querySelector('.project-grid-table-wrap')).toBeNull();
    });

    it('renders the error state instead of the table', () => {
        const {container} = render(<ProjectGridTable {...baseProps} error="Something went wrong" />);

        expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
        expect(container.querySelector('.project-grid-table-wrap')).toBeNull();
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
        expect(sortSelect).toHaveValue('class_code');
        expect(resultsBar.getByLabelText('Per page')).toBeInTheDocument();
        expect(resultsBar.getByRole('button', {name: 'View All Details'})).toHaveClass('itg-btn-text');

        fireEvent.change(sortSelect, {target: {value: 'project_title'}});
        expect(onSortChange).toHaveBeenCalledWith('project_title');
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
        expect(sortSelect).toHaveValue('industry');
        expect(within(sortSelect).getByRole('option', {name: 'Industry'})).toBeInTheDocument();
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

        fireEvent.click(screen.getByRole('button', {name: 'Clear search'}));
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

    it('defaults the no-results heading to an h2, whatever the link scope', () => {
        render(<ProjectGridTable {...baseProps} linkScope="past" pagedRows={[]} filteredCount={0} totalCount={2} />);

        expect(screen.getByRole('heading', {level: 2, name: 'No projects match the filters'})).toBeInTheDocument();
    });

    it('renders a custom search control instead of the default search input', () => {
        render(
            <ProjectGridTable {...baseProps} searchControl={<input aria-label="Custom search" />} />,
        );

        expect(screen.getByLabelText('Custom search')).toBeInTheDocument();
        expect(screen.queryByRole('searchbox')).toBeNull();
    });

    it('renders the controls status slot', () => {
        render(<ProjectGridTable {...baseProps} controlsStatus={<span>3 filtered</span>} />);

        expect(screen.getByText('3 filtered')).toBeInTheDocument();
    });

    it('toggles the View All Details / Hide All Details action', () => {
        const onToggleAllDetails = vi.fn();
        render(
            <ProjectGridTable {...baseProps} onToggleAllDetails={onToggleAllDetails} allDetailsExpanded={false} />,
        );

        const button = screen.getByRole('button', {name: 'View All Details'});
        fireEvent.click(button);
        expect(onToggleAllDetails).toHaveBeenCalledTimes(1);
    });

    it('shows Hide All Details when everything is expanded', () => {
        render(<ProjectGridTable {...baseProps} onToggleAllDetails={vi.fn()} allDetailsExpanded />);

        expect(screen.getByRole('button', {name: 'Hide All Details'})).toBeInTheDocument();
    });

    it('renders numbered pages and marks the current one', () => {
        const onPageChange = vi.fn();
        render(<ProjectGridTable {...baseProps} page={1} totalPages={3} onPageChange={onPageChange} />);

        const pages = within(screen.getByRole('navigation', {name: 'Pages'}));
        expect(pages.getByRole('button', {name: 'Page 2'})).toHaveAttribute('aria-current', 'page');
        expect(pages.getByRole('button', {name: 'Page 1'})).not.toHaveAttribute('aria-current');

        fireEvent.click(pages.getByRole('button', {name: 'Page 2'}));
        expect(onPageChange).not.toHaveBeenCalled();
        fireEvent.click(pages.getByRole('button', {name: 'Page 3'}));
        expect(onPageChange).toHaveBeenCalledWith(2);
    });

    it('renders pagination with correct disabled states', () => {
        const onPageChange = vi.fn();
        render(
            <ProjectGridTable
                {...baseProps}
                page={0}
                totalPages={3}
                onPageChange={onPageChange}
            />,
        );

        const previous = screen.getByRole('button', {name: 'Previous'});
        const next = screen.getByRole('button', {name: 'Next'});
        expect(previous).toBeDisabled();
        expect(next).toBeEnabled();
        expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();

        fireEvent.click(next);
        expect(onPageChange).toHaveBeenCalledWith(1);
    });

    it('goes back a page with Previous', () => {
        const onPageChange = vi.fn();
        render(<ProjectGridTable {...baseProps} page={2} totalPages={3} onPageChange={onPageChange} />);

        fireEvent.click(screen.getByRole('button', {name: 'Previous'}));
        expect(onPageChange).toHaveBeenCalledWith(1);
    });

    it('toggles selection and removes rows from the phone list', () => {
        const rows = makeRows(1);
        const onToggleSelected = vi.fn();
        const onDeleteRow = vi.fn();
        const {container} = render(
            <ProjectGridTable
                {...baseProps}
                rows={rows}
                pagedRows={rows}
                filteredCount={1}
                totalCount={1}
                selectable
                onToggleSelected={onToggleSelected}
                onDeleteRow={onDeleteRow}
            />,
        );

        const card = within(container.querySelector('.project-grid-mobile-card') as HTMLElement);
        fireEvent.click(card.getByRole('checkbox', {name: 'Select Project 1'}));
        expect(onToggleSelected).toHaveBeenCalledWith(rows[0].__key);
        fireEvent.click(card.getByRole('button', {name: 'Remove'}));
        expect(onDeleteRow).toHaveBeenCalledWith(rows[0]);
    });

    it('disables Next on the last page', () => {
        render(<ProjectGridTable {...baseProps} page={2} totalPages={3} onPageChange={vi.fn()} />);

        expect(screen.getByRole('button', {name: 'Next'})).toBeDisabled();
        expect(screen.getByRole('button', {name: 'Previous'})).toBeEnabled();
    });

    it('renders a select-all checkbox and per-row checkboxes when selectable', () => {
        const onToggleSelectAll = vi.fn();
        render(
            <ProjectGridTable
                {...baseProps}
                selectable
                selectedKeys={new Set()}
                onToggleSelected={vi.fn()}
                onToggleSelectAll={onToggleSelectAll}
            />,
        );

        fireEvent.click(screen.getAllByRole('checkbox', {name: /select all rows/i})[0]);
        expect(onToggleSelectAll).toHaveBeenCalledTimes(1);
    });

    it('renders per-row Remove buttons and forwards deletion', () => {
        const onDeleteRow = vi.fn();
        const rows = makeRows();
        render(<ProjectGridTable {...baseProps} rows={rows} onDeleteRow={onDeleteRow} />);

        const removeButtons = screen.getAllByRole('button', {name: 'Remove'});
        expect(removeButtons.length).toBeGreaterThan(0);
        fireEvent.click(removeButtons[0]);
        expect(onDeleteRow).toHaveBeenCalledWith(rows[0]);
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

        // The desktop table's navy square button is named "Hide" when expanded, "Details" when collapsed.
        const table = within(document.querySelector('.project-grid-table-wrap') as HTMLElement);
        const hide = table.getByRole('button', {name: 'Hide'});
        expect(hide).toHaveClass('project-grid-detail-icon-button');
        expect(hide).toHaveAttribute('aria-expanded', 'true');
        expect(hide.querySelector('.project-grid-detail-icon')).toHaveAttribute('aria-hidden', 'true');
        expect(table.getByRole('button', {name: 'Details'})).toHaveAttribute('aria-expanded', 'false');
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
        fireEvent.click(within(card).getByRole('button', {name: 'Show details'}));
        expect(baseProps.onToggleExpanded).toHaveBeenCalledWith(rows[0].__key);
    });
});

describe('getPagerItems', () => {
    it('lists every page when there are few', () => {
        expect(getPagerItems(0, 5)).toEqual([0, 1, 2, 3, 4]);
    });

    it('keeps the first, last and nearby pages and elides the rest', () => {
        expect(getPagerItems(0, 10)).toEqual([0, 1, 2, 3, 'gap-end', 9]);
        expect(getPagerItems(5, 10)).toEqual([0, 'gap-start', 4, 5, 6, 'gap-end', 9]);
        expect(getPagerItems(9, 10)).toEqual([0, 'gap-start', 6, 7, 8, 9]);
    });

    it('shows a single hidden page instead of an ellipsis', () => {
        expect(getPagerItems(3, 8)).toEqual([0, 1, 2, 3, 4, 'gap-end', 7]);
        expect(getPagerItems(4, 8)).toEqual([0, 'gap-start', 3, 4, 5, 6, 7]);
    });
});
