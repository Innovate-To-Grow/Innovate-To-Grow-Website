import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SearchTableCard} from '@/features/projects/components/search/cards/SearchTableCard';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// A Past Projects search table holds compact archive rows, which have no abstract. Its search also asks the server,
// which reads the abstracts, so a word that is only in an abstract still finds its project.

const {searchArchive} = vi.hoisted(() => ({searchArchive: vi.fn()}));
vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  searchPastProjectArchiveIds: searchArchive,
}));

const archiveRow = (index: number): ProjectGridRow => ({
  id: `11111111-1111-4111-8111-00000000000${index}`,
  semester_label: '2024-1 Spring',
  class_code: 'CAP',
  team_number: `${index}`,
  team_name: `Team ${index}`,
  project_title: `Project ${index}`,
  organization: 'Acme',
  industry: 'Energy',
  abstract: '',
  student_names: 'Ada',
  is_presenting: '',
});

const renderCard = () =>
  render(
    <SearchTableCard
      canRemove={false}
      initialRows={[archiveRow(1), archiveRow(2)]}
      tableId="table-1"
      title="Search Table"
      onRemove={vi.fn()}
      onMergeSelected={vi.fn()}
    />,
  );

describe('SearchTableCard server search', () => {
  afterEach(() => {
    cleanup();
    searchArchive.mockReset();
  });

  it('finds a project by a word in its abstract, saying it is still searching until the server answers', async () => {
    let answer!: (ids: ReadonlySet<string>) => void;
    searchArchive.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    renderCard();

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'EnergyPro'}});

    // No row's own text matches, but the server has not answered yet.
    expect(await screen.findByRole('heading', {name: 'No projects match “EnergyPro”'})).toBeInTheDocument();
    expect(screen.getByText('Still searching project abstracts…')).toBeInTheDocument();
    await vi.waitFor(() => expect(searchArchive).toHaveBeenCalledWith('EnergyPro', expect.any(AbortSignal)));

    answer(new Set([archiveRow(2).id!]));
    const table = await screen.findByRole('table', {name: 'Search Table'});
    expect(within(table).getByRole('link', {name: /Project 2/})).toBeInTheDocument();
    expect(within(table).queryByRole('link', {name: /Project 1/})).toBeNull();
    expect(screen.getByText('1 of 2')).toBeInTheDocument();
    expect(screen.queryByText('Still searching project abstracts…')).toBeNull();
  });

  it('says there are no matches once the server finds none either', async () => {
    searchArchive.mockResolvedValue(new Set());
    renderCard();

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'hydroponics'}});

    await vi.waitFor(() => expect(searchArchive).toHaveBeenCalled());
    await vi.waitFor(() => expect(screen.queryByText('Still searching project abstracts…')).toBeNull());
    expect(screen.getByRole('heading', {name: 'No projects match “hydroponics”'})).toBeInTheDocument();
  });
});
