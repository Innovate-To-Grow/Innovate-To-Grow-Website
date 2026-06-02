import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { ProjectTableBlock } from './ProjectTableBlock';

const renderBlock = (data: Record<string, unknown>) =>
  render(
    <MemoryRouter>
      <ProjectTableBlock data={data} />
    </MemoryRouter>,
  );

const sampleRows = [
  { Class: 'CAP', 'Team#': '201', TeamName: 'Almondry Trailer', 'Project Title': 'Hopper Mod',
    Organization: 'UC Merced', Industry: 'Agriculture', Abstract: 'A dryer.', 'Student Names': 'Arcadio Mercado' },
  { Class: 'CSE', 'Team#': '314', TeamName: 'The Curators', 'Project Title': 'Archive Tool',
    Organization: 'Library', Industry: 'Software' },
];

describe('ProjectTableBlock', () => {
  it('renders a heading and a searchable table with the provided rows', () => {
    const { container, getByText, getByPlaceholderText } = renderBlock({
      heading: 'Projects & Teams',
      rows: sampleRows,
    });
    expect(getByText('Projects & Teams')).toBeTruthy();
    expect(container.querySelector('.sdt-search')).not.toBeNull();
    expect(getByText('Almondry Trailer')).toBeTruthy();
    expect(getByText('The Curators')).toBeTruthy();
    // count reflects the row total
    expect(getByText('2 of 2 projects')).toBeTruthy();
    // search input is wired
    fireEvent.change(getByPlaceholderText('Search projects...'), { target: { value: 'Curators' } });
    expect(getByText('1 of 2 projects')).toBeTruthy();
  });

  it('renders an optional caption', () => {
    const { getByText } = renderBlock({ rows: sampleRows, caption: '34 teams' });
    expect(getByText('34 teams')).toBeTruthy();
  });

  it('renders an empty table when rows are missing or malformed', () => {
    const { container } = renderBlock({ heading: 'Empty' });
    expect(container.querySelector('.sdt-table')).not.toBeNull();
    expect(container.querySelector('.cms-project-table')).not.toBeNull();
  });

  it('coerces non-string row values without throwing', () => {
    const { getByText } = renderBlock({ rows: [{ Class: 'CAP', 'Team#': 205, TeamName: null }] });
    expect(getByText('1 of 1 projects')).toBeTruthy();
  });
});
