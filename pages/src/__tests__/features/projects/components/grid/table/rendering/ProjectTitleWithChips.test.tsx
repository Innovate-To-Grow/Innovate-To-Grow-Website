import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import type {ProjectGridLinkScope, ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {ProjectTitleWithChips} from '@/features/projects/components/grid/table/ProjectTitleWithChips';

const row: ProjectGridRow = {
  id: '33333333-3333-4333-8333-333333333333',
  semester_label: '2026 Fall',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Campus Water Sensor',
  organization: 'Acme',
  industry: 'Water',
  abstract: '',
  student_names: '',
  is_presenting: 'Yes',
  catalog: 'current',
};

const renderTitle = (
  rowProps: Partial<ProjectGridRow> = {},
  scope: ProjectGridLinkScope = 'past',
  tags: {isNew?: boolean; isSaved?: boolean} = {},
) =>
  render(
    <ProjectTitleWithChips
      row={{...row, ...rowProps}}
      scope={scope}
      isNew={tags.isNew ?? false}
      isSaved={tags.isSaved ?? false}
      savedRowLabel="Added"
    />,
  );

describe('ProjectTitleWithChips', () => {
  afterEach(() => {
    cleanup();
  });

  it('tags a current-schedule row "Current" in a list that mixes catalogs', () => {
    const {container} = renderTitle();

    const tag = screen.getByText('Current');
    expect(tag).toHaveClass('itg-tag', 'itg-tag-current', 'project-grid-row-chip', 'is-current');
    // Its text is the tag's only child (page translation swaps text nodes), and it is not part of the link's name.
    expect(tag.childNodes).toHaveLength(1);
    expect(screen.getByRole('link')).toHaveAccessibleName('Campus Water Sensor (opens in a new tab)');
    expect(container.querySelector('.project-grid-title-line')?.lastElementChild).toBe(tag);
  });

  it('tags a current row that has no project page too', () => {
    renderTitle({id: undefined});

    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('Current')).toHaveClass('itg-tag-current');
  });

  it('puts Current before the New and Added tags', () => {
    const {container} = renderTitle({}, 'past', {isNew: true, isSaved: true});

    const tags = Array.from(container.querySelectorAll('.project-grid-row-chip')).map((tag) => tag.textContent);
    expect(tags).toEqual(['Current', 'New', 'Added']);
  });

  it('leaves archive rows, and rows stored without a catalog, untagged', () => {
    renderTitle({catalog: 'archive'});
    expect(screen.queryByText('Current')).toBeNull();
    cleanup();

    renderTitle({catalog: undefined});
    expect(screen.queryByText('Current')).toBeNull();
  });

  it('never tags the rows of the Current and Presenting lists, which hold one catalog', () => {
    renderTitle({}, 'current');

    expect(screen.getByRole('link', {name: 'Campus Water Sensor'})).toBeInTheDocument();
    expect(screen.queryByText('Current')).toBeNull();
  });
});
