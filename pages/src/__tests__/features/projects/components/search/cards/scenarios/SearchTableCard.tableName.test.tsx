import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SearchTableCard} from '@/features/projects/components/search/cards/SearchTableCard';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// With several search tables on Past Projects, each table and its pager are named after the card's title instead
// of being one more unnamed table and one more "Pages" landmark.

const makeRows = (count: number): ProjectGridRow[] =>
  Array.from({length: count}, (_, index) => ({
    semester_label: '2025-1 Spring',
    class_code: 'CAP',
    team_number: `${index + 1}`,
    team_name: `Team ${index + 1}`,
    project_title: `Project ${index + 1}`,
    organization: 'Acme',
    industry: 'Energy',
    abstract: 'An abstract',
    student_names: 'Ada',
    is_presenting: '',
  }));

const renderCard = (tableId: string, title: string) => (
  <SearchTableCard
    canRemove
    initialRows={makeRows(6)}
    tableId={tableId}
    title={title}
    onRemove={vi.fn()}
    onMergeSelected={vi.fn()}
  />
);

describe('SearchTableCard table name', () => {
  afterEach(() => cleanup());

  it('names each table and its pager after the card title', () => {
    render(
      <>
        {renderCard('table-1', 'Search Table')}
        {renderCard('table-2', 'Search Table 2')}
      </>,
    );

    expect(screen.getByRole('table', {name: 'Search Table'})).toBeInTheDocument();
    expect(screen.getByRole('table', {name: 'Search Table 2'})).toBeInTheDocument();
    expect(screen.getByRole('navigation', {name: 'Search Table pages'})).toBeInTheDocument();
    expect(screen.getByRole('navigation', {name: 'Search Table 2 pages'})).toBeInTheDocument();
    expect(screen.queryByRole('navigation', {name: 'Pages'})).toBeNull();
  });
});
