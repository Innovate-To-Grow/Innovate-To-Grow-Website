import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProjectGridTable} from '@/features/projects/components/grid/table/ProjectGridTable';
import {getPagerItems} from '@/features/projects/components/grid/controls/pagerItems';
import {
    PAST_PROJECT_GRID_COLUMNS,
    createProjectGridItems,
    type ProjectGridColumnKey,
    type ProjectGridItem,
    type ProjectGridRow,
    type ProjectGridSortDirection,
} from '@/features/projects/components/grid/contracts/projectGrid';

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

describe('ProjectGridTable pager', () => {
    afterEach(() => {
        cleanup();
        vi.restoreAllMocks();
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

    it('after a pager click, focuses the count and scrolls the top of the new page into view', () => {
        const scrollIntoView = vi.fn();
        Element.prototype.scrollIntoView = scrollIntoView;
        const props = {...baseProps, totalPages: 3, onPageChange: vi.fn()};
        const {container, rerender} = render(<ProjectGridTable {...props} page={1} />);
        const count = container.querySelector('.project-grid-count') as HTMLElement;
        // The visitor has scrolled down to the pager: the count line is far above the viewport.
        vi.spyOn(count, 'getBoundingClientRect').mockReturnValue({top: -1600} as DOMRect);

        const next = screen.getByRole('button', {name: 'Next'});
        next.focus();
        fireEvent.click(next);
        expect(props.onPageChange).toHaveBeenCalledWith(2);
        rerender(<ProjectGridTable {...props} page={2} />);

        // Next is now disabled; focus did not fall to the page.
        expect(screen.getByRole('button', {name: 'Next'})).toBeDisabled();
        expect(document.activeElement).toBe(count);
        expect(count).toHaveAttribute('tabindex', '-1');
        expect(scrollIntoView).toHaveBeenCalledWith({block: 'start'});
        Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
    });

    it('leaves focus and scroll alone when the page changes for another reason, or the count is in view', () => {
        const scrollIntoView = vi.fn();
        Element.prototype.scrollIntoView = scrollIntoView;
        const props = {...baseProps, totalPages: 3, onPageChange: vi.fn()};
        const {container, rerender} = render(<ProjectGridTable {...props} page={2} />);
        const count = container.querySelector('.project-grid-count') as HTMLElement;

        // A new search starts over on page 1: no pager click.
        rerender(<ProjectGridTable {...props} page={0} />);
        expect(document.activeElement).not.toBe(count);

        // The count line is on screen: focus moves, the page does not scroll.
        vi.spyOn(count, 'getBoundingClientRect').mockReturnValue({top: 200} as DOMRect);
        fireEvent.click(screen.getByRole('button', {name: 'Page 2'}));
        rerender(<ProjectGridTable {...props} page={1} />);
        expect(document.activeElement).toBe(count);
        expect(scrollIntoView).not.toHaveBeenCalled();
        Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
    });

    it('disables Next on the last page', () => {
        render(<ProjectGridTable {...baseProps} page={2} totalPages={3} onPageChange={vi.fn()} />);

        expect(screen.getByRole('button', {name: 'Next'})).toBeDisabled();
        expect(screen.getByRole('button', {name: 'Previous'})).toBeEnabled();
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
