import {fireEvent, render, screen} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {PROJECT_GRID_COLUMNS, type ProjectGridItem} from '@/features/projects/components/projectGrid';
import {ProjectGridTable} from '@/features/projects/components/ProjectGridTable';

const row = (key: string, title: string): ProjectGridItem => ({
  __key: key,
  semester_label: '2026 Spring',
  class_code: 'CSE',
  team_number: key,
  team_name: `${title} Team`,
  project_title: title,
  organization: 'UC Merced',
  industry: 'Education',
  abstract: 'Abstract',
  student_names: 'Ada Lovelace',
  is_presenting: 'Yes',
});

const rows = [row('101', 'Robot'), row('102', 'Sensor')];

describe('ProjectGridTable', () => {
  beforeEach(() => {
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0);
      return 0;
    });
  });

  it('renders controls, table rows, pagination, and toolbar actions', () => {
    const onSearchChange = vi.fn();
    const onSortChange = vi.fn();
    const onToggleExpanded = vi.fn();
    const onToggleAllDetails = vi.fn();
    const onPageChange = vi.fn();
    const onPageSizeChange = vi.fn();
    const onToggleSelected = vi.fn();
    const onToggleSelectAll = vi.fn();
    const onDeleteRow = vi.fn();

    render(
      <ProjectGridTable
        columns={PROJECT_GRID_COLUMNS}
        rows={rows}
        pagedRows={rows}
        filteredCount={2}
        totalCount={5}
        search="robot"
        controlsStatus={<span>Status ready</span>}
        sortField="project_title"
        sortDirection="asc"
        onSearchChange={onSearchChange}
        onSortChange={onSortChange}
        expandedKeys={new Set()}
        onToggleExpanded={onToggleExpanded}
        onToggleAllDetails={onToggleAllDetails}
        allDetailsExpanded={false}
        page={1}
        totalPages={3}
        onPageChange={onPageChange}
        pageSize={10}
        pageSizeOptions={[5, 10, 25]}
        onPageSizeChange={onPageSizeChange}
        toolbar={<button type="button">Toolbar action</button>}
        toolbarPlacement="bottom"
        selectable
        selectedKeys={new Set(['101'])}
        onToggleSelected={onToggleSelected}
        onToggleSelectAll={onToggleSelectAll}
        onDeleteRow={onDeleteRow}
      />,
    );

    fireEvent.change(screen.getByLabelText('Search'), {target: {value: 'sensor'}});
    expect(onSearchChange).toHaveBeenCalledWith('sensor');
    expect(screen.getByText('2 of 5')).toBeInTheDocument();
    expect(screen.getByText('Status ready')).toBeInTheDocument();
    expect(screen.getByText('Toolbar action')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Show All Details'}));
    expect(onToggleAllDetails).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', {name: 'Per page 10'}));
    fireEvent.click(screen.getByRole('option', {name: '25'}));
    expect(onPageSizeChange).toHaveBeenCalledWith(25);

    fireEvent.click(screen.getByRole('button', {name: 'Previous'}));
    fireEvent.click(screen.getByRole('button', {name: 'Next'}));
    expect(onPageChange).toHaveBeenCalledWith(0);
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it('renders loading, error, and empty states without grid rows', () => {
    const common = {
      columns: PROJECT_GRID_COLUMNS,
      rows: [],
      pagedRows: [],
      filteredCount: 0,
      totalCount: 0,
      search: '',
      sortField: 'project_title' as const,
      sortDirection: 'asc' as const,
      onSearchChange: vi.fn(),
      onSortChange: vi.fn(),
      expandedKeys: new Set<string>(),
      onToggleExpanded: vi.fn(),
      page: 0,
      totalPages: 1,
      onPageChange: vi.fn(),
      pageSize: 10,
      pageSizeOptions: [10],
      onPageSizeChange: vi.fn(),
    };

    const loading = render(<ProjectGridTable {...common} loading />);
    expect(screen.getByText('Loading project data...')).toBeInTheDocument();
    loading.unmount();

    const error = render(<ProjectGridTable {...common} error="Projects failed" />);
    expect(screen.getByText('Projects failed')).toBeInTheDocument();
    error.unmount();

    render(<ProjectGridTable {...common} emptyMessage="Nothing here" />);
    expect(screen.getAllByText('Nothing here').length).toBeGreaterThan(0);
  });

  it('supports keyboard navigation and outside-click dismissal in the page-size selector', () => {
    const onPageSizeChange = vi.fn();
    const common = {
      columns: PROJECT_GRID_COLUMNS,
      rows,
      pagedRows: rows,
      filteredCount: 2,
      totalCount: 2,
      search: '',
      sortField: 'project_title' as const,
      sortDirection: 'asc' as const,
      onSearchChange: vi.fn(),
      onSortChange: vi.fn(),
      expandedKeys: new Set<string>(),
      onToggleExpanded: vi.fn(),
      page: 0,
      totalPages: 1,
      onPageChange: vi.fn(),
      pageSize: 10,
      pageSizeOptions: [5, 10, 25],
      onPageSizeChange,
    };

    render(<ProjectGridTable {...common} />);
    const button = screen.getByRole('button', {name: 'Per page 10'});

    fireEvent.keyDown(button, {key: 'ArrowDown'});
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    screen.getByRole('option', {name: '25'}).focus();
    fireEvent.keyDown(screen.getByRole('option', {name: '25'}), {key: 'ArrowUp'});
    expect(screen.getByRole('option', {name: '10'})).toHaveFocus();

    fireEvent.keyDown(screen.getByRole('option', {name: '10'}), {key: 'Home'});
    expect(screen.getByRole('option', {name: '5'})).toHaveFocus();

    fireEvent.keyDown(screen.getByRole('option', {name: '5'}), {key: 'End'});
    expect(screen.getByRole('option', {name: '25'})).toHaveFocus();

    fireEvent.keyDown(screen.getByRole('option', {name: '25'}), {key: 'Escape'});
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(button).toHaveFocus();

    fireEvent.keyDown(button, {key: 'Enter'});
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole('listbox')).toBeNull();

    fireEvent.keyDown(button, {key: 'ArrowUp'});
    screen.getByRole('option', {name: '5'}).focus();
    fireEvent.click(screen.getByRole('option', {name: '5'}));
    expect(onPageSizeChange).toHaveBeenCalledWith(5);
    expect(button).toHaveFocus();

    fireEvent.keyDown(button, {key: ' '});
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    fireEvent.keyDown(button, {key: ' '});
    expect(screen.queryByRole('listbox')).toBeNull();
  });
});
