import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/ProjectGridTable';
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

    it('renders the search input and reports row counts with a label', () => {
        render(<ProjectGridTable {...baseProps} />);

        expect(screen.getByPlaceholderText('Search projects...')).toBeInTheDocument();
        expect(screen.getByText('2 of 2')).toBeInTheDocument();
        expect(screen.getByText('projects')).toBeInTheDocument();
    });

    it('uses a custom search placeholder and count label', () => {
        render(<ProjectGridTable {...baseProps} searchPlaceholder="Find entries..." countLabel="entries" />);

        expect(screen.getByPlaceholderText('Find entries...')).toBeInTheDocument();
        expect(screen.getByText('entries')).toBeInTheDocument();
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
        const titleHeader = within(table).getByRole('columnheader', {name: /project title/i});
        fireEvent.click(within(titleHeader).getByRole('button'));
        expect(onSortChange).toHaveBeenCalledWith('project_title');
    });

    it('renders the loading state instead of the table', () => {
        const {container} = render(<ProjectGridTable {...baseProps} loading />);

        expect(screen.getByText('Loading project data...')).toBeInTheDocument();
        expect(container.querySelector('.project-grid-table-wrap')).toBeNull();
    });

    it('renders the error state instead of the table', () => {
        const {container} = render(<ProjectGridTable {...baseProps} error="Something went wrong" />);

        expect(screen.getByText('Something went wrong')).toBeInTheDocument();
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

    it('renders the toolbar at the top by default and at the bottom when requested', () => {
        const toolbar = <button type="button">Export</button>;
        const {container, rerender} = render(<ProjectGridTable {...baseProps} toolbar={toolbar} />);

        const topShell = container.querySelector('.project-grid-table-shell');
        expect(topShell?.firstElementChild?.className).toContain('project-grid-toolbar');

        rerender(<ProjectGridTable {...baseProps} toolbar={toolbar} toolbarPlacement="bottom" />);
        expect(container.querySelector('.project-grid-toolbar--bottom')).not.toBeNull();
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

        // The desktop table uses "Hide" when expanded, "View" when collapsed.
        fireEvent.click(screen.getAllByRole('button', {name: 'Hide'})[0]);
        expect(onToggleExpanded).toHaveBeenCalledWith(rows[0].__key);
    });

    describe('PageSizeSelect', () => {
        it('opens the menu and picks a new page size', () => {
            const onPageSizeChange = vi.fn();
            render(<ProjectGridTable {...baseProps} onPageSizeChange={onPageSizeChange} />);

            const trigger = screen.getByRole('button', {name: /per page/i});
            expect(trigger).toHaveAttribute('aria-expanded', 'false');

            fireEvent.click(trigger);
            expect(trigger).toHaveAttribute('aria-expanded', 'true');

            fireEvent.click(screen.getByRole('option', {name: '10'}));
            expect(onPageSizeChange).toHaveBeenCalledWith(10);
        });

        it('opens the menu with ArrowDown and Enter on the trigger', () => {
            render(<ProjectGridTable {...baseProps} />);
            const trigger = screen.getByRole('button', {name: /per page/i});

            fireEvent.keyDown(trigger, {key: 'ArrowDown'});
            expect(trigger).toHaveAttribute('aria-expanded', 'true');

            fireEvent.keyDown(trigger, {key: 'Enter'});
            // Enter while open closes the menu.
            expect(trigger).toHaveAttribute('aria-expanded', 'false');
        });

        it('opens with Space and closes with Escape on an option', () => {
            render(<ProjectGridTable {...baseProps} />);
            const trigger = screen.getByRole('button', {name: /per page/i});

            fireEvent.keyDown(trigger, {key: ' '});
            expect(trigger).toHaveAttribute('aria-expanded', 'true');

            const option = screen.getByRole('option', {name: '10'});
            fireEvent.keyDown(option, {key: 'Escape'});
            expect(trigger).toHaveAttribute('aria-expanded', 'false');
        });

        it('marks the selected option and closes when clicking outside', () => {
            render(<ProjectGridTable {...baseProps} />);
            const trigger = screen.getByRole('button', {name: /per page/i});

            fireEvent.click(trigger);
            const selected = screen.getByRole('option', {name: '5'});
            expect(selected).toHaveAttribute('aria-selected', 'true');
            expect(selected).toHaveClass('is-selected');

            fireEvent.pointerDown(document.body);
            expect(trigger).toHaveAttribute('aria-expanded', 'false');
        });

        it('navigates options with Home and End without crashing', () => {
            render(<ProjectGridTable {...baseProps} />);
            fireEvent.click(screen.getByRole('button', {name: /per page/i}));

            const option = screen.getByRole('option', {name: '5'});
            fireEvent.keyDown(option, {key: 'Home'});
            fireEvent.keyDown(option, {key: 'End'});
            fireEvent.keyDown(option, {key: 'ArrowDown'});
            fireEvent.keyDown(option, {key: 'ArrowUp'});

            expect(screen.getByRole('button', {name: /per page/i})).toHaveAttribute('aria-expanded', 'true');
        });
    });
});
