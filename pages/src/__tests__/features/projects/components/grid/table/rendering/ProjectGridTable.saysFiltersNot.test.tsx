import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/grid/table/ProjectGridTable';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';
import {baseProps, makeRows} from '@/__tests__/features/projects/components/grid/table/rendering/projectGridTableFixtures';

describe('ProjectGridTable', () => {
    afterEach(() => {
        cleanup();
        vi.unstubAllGlobals();
    });

    it('says the filters, not only the search, narrowed the rows', () => {
        const rows = makeRows(1);
        const {container, rerender} = render(
            <ProjectGridTable
                {...baseProps}
                search="a"
                pagedRows={rows}
                filteredCount={1}
                totalCount={75}
                activeFilters={['AeroSpace']}
            />,
        );
        expect(container.querySelector('.project-grid-count')).toHaveTextContent(
            /^1 of 75 projects matches “a” in AeroSpace · showing 1–1$/,
        );

        rerender(
            <ProjectGridTable
                {...baseProps}
                pagedRows={rows}
                filteredCount={1}
                totalCount={75}
                activeFilters={['Engineering Capstone (CAP)', 'AeroSpace']}
            />,
        );
        expect(container.querySelector('.project-grid-count')).toHaveTextContent(
            /^1 of 75 projects in Engineering Capstone \(CAP\) and AeroSpace · showing 1–1$/,
        );
    });

    it('blames the filters in the no-results state when they are in use, and clears them', () => {
        const onSearchChange = vi.fn();
        const onClearFilters = vi.fn();
        const noResults = {...baseProps, pagedRows: [], filteredCount: 0, totalCount: 75, onSearchChange, onClearFilters};
        const {container, rerender} = render(
            <ProjectGridTable
                {...noResults}
                search="CSE"
                activeFilters={['Engineering Capstone (CAP)']}
                noResultsHint="Older projects are in Past Projects."
            />,
        );

        expect(
            screen.getByRole('heading', {level: 2, name: 'No projects match “CSE” in Engineering Capstone (CAP)'}),
        ).toBeInTheDocument();
        expect(container.querySelector('.itg-empty-state-text')).toHaveTextContent(
            /^Clear the filters to search all projects, or check the spelling\. Older projects are in Past Projects\.$/,
        );
        expect(container.querySelector('.project-grid-count')).toHaveTextContent(
            /^0 of 75 projects match “CSE” in Engineering Capstone \(CAP\)$/,
        );
        fireEvent.click(screen.getByRole('button', {name: 'Clear Search and Filters'}));
        expect(onSearchChange).toHaveBeenCalledWith('');
        expect(onClearFilters).toHaveBeenCalledTimes(1);

        rerender(<ProjectGridTable {...noResults} countLabel="teams" activeFilters={['Software Engineering Capstone (CSE)', 'Construction']} />);
        expect(
            screen.getByRole('heading', {name: 'No teams in Software Engineering Capstone (CSE) and Construction'}),
        ).toBeInTheDocument();
        expect(screen.getByText('Clear the filters to see all teams.')).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Clear Filters'})).toBeInTheDocument();
    });

    it('suggests what a search can find when no filter is in use', () => {
        render(<ProjectGridTable {...baseProps} search="zzz" pagedRows={[]} filteredCount={0} totalCount={2} />);

        expect(
            screen.getByText('Check the spelling, or try a project title, team, organization, industry or student name.'),
        ).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Clear Search'})).toBeInTheDocument();
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

    it('toggles selection and removes rows from the phone list', () => {
        stubGridLayout('phone');
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
        fireEvent.click(card.getByRole('button', {name: 'Remove Project 1'}));
        expect(onDeleteRow).toHaveBeenCalledWith(rows[0]);
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

        const removeButtons = screen.getAllByRole('button', {name: /^Remove /});
        expect(removeButtons.length).toBeGreaterThan(0);
        fireEvent.click(removeButtons[0]);
        expect(onDeleteRow).toHaveBeenCalledWith(rows[0]);
    });
});
