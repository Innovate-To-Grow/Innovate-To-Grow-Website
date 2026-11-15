import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/grid/table/ProjectGridTable';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';
import {baseProps, makeRows} from '@/__tests__/features/projects/components/grid/table/rendering/projectGridTableFixtures';

describe('ProjectGridTable', () => {
    afterEach(() => {
        cleanup();
        vi.unstubAllGlobals();
    });

    it('renders only the layout the screen shows, and switches when the screen crosses the breakpoint', () => {
        const layout = stubGridLayout('desktop');
        const {container} = render(<ProjectGridTable {...baseProps} />);

        // Hiding the other layout with CSS doubled every row and its opened details.
        expect(container.querySelectorAll('tr.project-grid-row')).toHaveLength(2);
        expect(container.querySelector('.project-grid-mobile-cards')).toBeNull();

        act(() => layout.setPhone(true));
        expect(container.querySelectorAll('.project-grid-mobile-card')).toHaveLength(2);
        expect(container.querySelector('.project-grid-table-wrap')).toBeNull();
    });

    it('renders a labelled search field and reports the row count and the rows shown', () => {
        const {container} = render(<ProjectGridTable {...baseProps} />);

        expect(screen.getByLabelText('Search')).toHaveAttribute('placeholder', 'Search projects…');
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

    it('says in the count line when the search term is too common for the abstracts to be searched', () => {
        const rows = makeRows(1);
        const note = 'Abstracts were not searched: this search term is too common. Try a longer one.';
        const serverSearch = {pending: false, addedRowsKey: null, tooBroad: true, failed: false};
        const {container, rerender} = render(
            <ProjectGridTable {...baseProps} search="team" serverSearch={serverSearch} pagedRows={rows} filteredCount={1} />,
        );
        const count = container.querySelector('.project-grid-count') as HTMLElement;

        // Inside the count's live region, so it is read out with it.
        expect(within(count).getByText(note)).toBeInTheDocument();
        expect(count).toHaveTextContent('1 of 2 projects matches “team” · showing 1–1');

        // With no rows matching either.
        rerender(
            <ProjectGridTable {...baseProps} search="system" serverSearch={serverSearch} pagedRows={[]} filteredCount={0} />,
        );
        expect(within(container.querySelector('.project-grid-count') as HTMLElement).getByText(note)).toBeInTheDocument();

        // A search the server did search says nothing more.
        rerender(
            <ProjectGridTable
                {...baseProps}
                search="water"
                serverSearch={{...serverSearch, tooBroad: false}}
                pagedRows={rows}
                filteredCount={1}
            />,
        );
        expect(screen.queryByText(note)).toBeNull();
    });

    it('says in the count line when the abstracts could not be searched, so no rows found is not a true zero', () => {
        const note = 'Abstracts were not searched: something went wrong. Change the search to try again.';
        const serverSearch = {pending: false, addedRowsKey: null, tooBroad: false, failed: true};
        const {container} = render(
            <ProjectGridTable {...baseProps} search="Denver" serverSearch={serverSearch} pagedRows={[]} filteredCount={0} />,
        );
        const count = container.querySelector('.project-grid-count') as HTMLElement;

        expect(within(count).getByText(note)).toBeInTheDocument();
        expect(count).toHaveTextContent('0 of 2 projects match “Denver”');
        expect(screen.queryByText(/this search term is too common/)).toBeNull();
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

    it('marks the sorted header, and only the header', () => {
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

        // The arrow and aria-sort mark the sorted column: its cells are not shaded.
        const organizationCells = container.querySelectorAll('tbody td.project-grid-col-organization');
        expect(organizationCells).toHaveLength(2);
        organizationCells.forEach((cell) => expect(cell.className).toBe('project-grid-col-organization'));
        // The details column is headed "Details", as on the reference table.
        expect(table.getByRole('columnheader', {name: 'Details'})).toBeInTheDocument();
    });

    it('renders the loading state instead of the table', () => {
        const {container} = render(<ProjectGridTable {...baseProps} loading />);

        // The shared loading indicator, inside the line's own status role.
        const status = screen.getByRole('status');
        expect(status).toHaveClass('project-grid-state-loading');
        expect(status).toHaveTextContent('Loading project data…');
        expect(status.querySelector('.loading-indicator-spinner')).toHaveAttribute('aria-hidden', 'true');
        expect(container.querySelector('.project-grid-table-wrap')).toBeNull();
    });

    it('renders the error state instead of the table', () => {
        const {container} = render(<ProjectGridTable {...baseProps} error="Something went wrong" />);

        expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
        expect(container.querySelector('.project-grid-table-wrap')).toBeNull();
        expect(screen.queryByRole('button', {name: 'Try Again'})).toBeNull();
    });

    it('offers to load the rows again after an error', () => {
        const onRetry = vi.fn();
        render(<ProjectGridTable {...baseProps} error="We couldn't load the projects." onRetry={onRetry} />);

        const tryAgain = screen.getByRole('button', {name: 'Try Again'});
        expect(tryAgain).toHaveClass('itg-btn', 'itg-btn-outline');
        fireEvent.click(tryAgain);
        expect(onRetry).toHaveBeenCalledTimes(1);
    });
});
