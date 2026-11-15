import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SearchTableCard} from '@/features/projects/components/search/cards/SearchTableCard';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// With several search tables open, each repeats the same controls (Search, Per page, Pages, Add to Curation…).

const makeRows = (count: number): ProjectGridRow[] =>
  Array.from({length: count}, (_, index) => ({
    semester_label: '2025-1 Spring',
    class_code: 'ENGR 120',
    team_number: `T${String(index + 1).padStart(2, '0')}`,
    team_name: `Team ${index + 1}`,
    project_title: `Project ${index + 1}`,
    organization: 'Acme',
    industry: 'Technology',
    abstract: 'An abstract',
    student_names: 'Alice',
    is_presenting: '',
  }));

const renderCards = () =>
  render(
    <>
      <SearchTableCard canRemove initialRows={makeRows(12)} tableId="table-1" title="Search Table" onRemove={vi.fn()} onMergeSelected={vi.fn()} />
      <SearchTableCard canRemove initialRows={makeRows(3)} tableId="table-2" title="Search Table 2" onRemove={vi.fn()} onMergeSelected={vi.fn()} />
    </>,
  );

describe('SearchTableCard — telling one table from another', () => {
  afterEach(() => {
    cleanup();
  });

  it("is a region named after its heading, holding that table's controls", () => {
    renderCards();

    const second = screen.getByRole('region', {name: 'Search Table 2'});
    expect(within(second).getByRole('searchbox')).toBeInTheDocument();
    expect(within(second).getByRole('button', {name: 'Delete Table: Search Table 2'})).toBeInTheDocument();
    expect(screen.getByRole('region', {name: 'Search Table'})).not.toContainElement(within(second).getByRole('searchbox'));
  });

  it('names its save groups after what the button does, above and below the table', () => {
    renderCards();
    const first = within(screen.getByRole('region', {name: 'Search Table'}));
    fireEvent.change(first.getByLabelText('Per page'), {target: {value: '10'}});

    expect(first.getByRole('group', {name: 'Add to Curation'})).toContainElement(
      first.getAllByRole('button', {name: 'Add to Curation'})[0],
    );
    expect(first.getByRole('group', {name: 'Add to Curation below the table'})).toBeInTheDocument();
    expect(first.queryByRole('group', {name: 'Save'})).toBeNull();
  });

  it('tells screen readers how many rows Select All checked, on pages they cannot see too', () => {
    renderCards();
    const region = screen.getByRole('region', {name: 'Search Table'});
    // Beside the card's status (its save outcome): a polite region of its own.
    const announcer = region.querySelector('.sr-only[aria-live="polite"]:not([role])') as HTMLElement;
    expect(announcer).toBeEmptyDOMElement();

    fireEvent.click(within(region).getByRole('button', {name: 'Select All'}));
    expect(announcer).toHaveTextContent('12 projects selected');

    fireEvent.change(within(region).getByRole('searchbox'), {target: {value: 'Project 12'}});
    expect(announcer).toHaveTextContent('12 projects selected, 11 of them not shown by the current search');
  });
});
