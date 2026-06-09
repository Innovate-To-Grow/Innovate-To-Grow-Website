import {act, renderHook} from '@testing-library/react';
import {describe, expect, it} from 'vitest';

import {useProjectGridTable} from '@/features/projects/components/useProjectGridTable';
import type {ProjectGridItem} from '@/features/projects/components/projectGrid';

const row = (key: string, title: string, abstract = ''): ProjectGridItem => ({
  __key: key,
  semester_label: '2026 Spring',
  class_code: key === 'b' ? 'BIO' : 'CSE',
  team_number: key === 'b' ? '2' : '1',
  team_name: `${title} team`,
  project_title: title,
  organization: key === 'b' ? 'Lab' : 'UC Merced',
  industry: 'Education',
  abstract,
  student_names: abstract ? 'Ada Lovelace' : '',
  is_presenting: key === 'b' ? 'No' : 'Yes',
});

const rows = [row('a', 'Alpha', 'Has detail'), row('b', 'Beta'), row('c', 'Gamma', 'More detail')];

describe('useProjectGridTable', () => {
  it('filters, sorts, pages, expands details, and tracks selected rows', () => {
    const {result, rerender} = renderHook(
      ({initialSearch}) =>
        useProjectGridTable({
          rows,
          defaultSortField: 'project_title',
          initialSearch,
          pageSize: 2,
          pageSizeOptions: [1],
          expandAllByDefault: true,
        }),
      {initialProps: {initialSearch: ''}},
    );

    expect(result.current.pageSizeOptions).toEqual([1, 2]);
    expect(result.current.totalPages).toBe(2);
    expect(result.current.allDetailsExpanded).toBe(true);

    act(() => result.current.toggleSort('project_title'));
    expect(result.current.sortDirection).toBe('desc');
    expect(result.current.pagedRows[0].project_title).toBe('Gamma');

    act(() => result.current.setSearch('lab'));
    expect(result.current.filteredRows.map((item) => item.__key)).toEqual(['b']);
    expect(result.current.totalPages).toBe(1);

    act(() => result.current.toggleSelected('b'));
    expect(result.current.selectedRows.map((item) => item.__key)).toEqual(['b']);
    expect(result.current.keepSelectedRows(rows).map((item) => item.__key)).toEqual(['b']);
    expect(result.current.removeSelectedRows(rows).map((item) => item.__key)).toEqual(['a', 'c']);

    act(() => result.current.clearSelection());
    expect(result.current.hasSelection).toBe(false);

    act(() => result.current.selectAllRows());
    expect(result.current.selectedRows).toHaveLength(3);

    rerender({initialSearch: 'alpha'});
    expect(result.current.search).toBe('alpha');

    act(() => result.current.setPageSize(0));
    expect(result.current.pageSize).toBe(1);
  });
});
