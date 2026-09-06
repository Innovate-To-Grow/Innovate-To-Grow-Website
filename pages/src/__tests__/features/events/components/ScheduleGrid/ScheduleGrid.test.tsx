import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ScheduleGrid} from '@/features/events/components/ScheduleGrid';
import type {ClassConfig} from '@/features/events/components/ScheduleGrid';
import type {SheetRow, TrackInfo} from '@/components/SheetsDataTable';

const classes: ClassConfig[] = [
  {
    code: 'CAP',
    label: 'Capstone',
    trackCount: 2,
    orderCount: 2,
    startTime: '1:00',
    slotMinutes: 30,
    trackLabels: ['TrackA', 'TrackB'],
  },
  {
    code: 'CSE',
    label: 'Software',
    trackCount: 1,
    orderCount: 1,
    startTime: '2:00',
    slotMinutes: 20,
    trackLabels: ['TrackC'],
    accentColor: '#FFBF3C',
  },
];

const trackInfos: TrackInfo[] = [
  {name: 't1', room: 'Room A', zoomLink: ''},
  {name: 't2', room: 'Room B', zoomLink: ''},
  {name: 't3', room: 'Room C', zoomLink: ''},
];

const makeRow = (overrides: Partial<SheetRow> = {}): SheetRow => ({
  Track: '1',
  Order: '1',
  'Year-Semester': '2025 Spring',
  Class: 'CAP',
  'Team#': 'CAP-101',
  TeamName: 'Team A',
  'Project Title': 'Project A',
  Organization: 'Org A',
  Industry: 'Energy',
  Abstract: '',
  'Student Names': '',
  'Showcase Participation': '',
  NameTitle: 'CAP Team A',
  ...overrides,
});

describe('ScheduleGrid', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the loading state', () => {
    render(<ScheduleGrid classes={[]} rows={[]} trackInfos={[]} loading />);

    expect(screen.getByText('Loading schedule...')).toBeInTheDocument();
  });

  it('renders the error state', () => {
    render(<ScheduleGrid classes={[]} rows={[]} trackInfos={[]} error="Failed to load" />);

    expect(screen.getByText('Failed to load')).toBeInTheDocument();
  });

  it('prefers loading over error when both are set', () => {
    render(<ScheduleGrid classes={[]} rows={[]} trackInfos={[]} loading error="Failed to load" />);

    expect(screen.getByText('Loading schedule...')).toBeInTheDocument();
    expect(screen.queryByText('Failed to load')).toBeNull();
  });

  it('renders an empty grid with empty room cells when track info is missing', () => {
    const {container} = render(<ScheduleGrid classes={classes} rows={[]} trackInfos={[]} />);

    expect(screen.getByText('Capstone (CAP)')).toBeInTheDocument();
    expect(screen.getByText('Software (CSE)')).toBeInTheDocument();

    const roomCells = container.querySelectorAll('.sg-th-room');
    expect(roomCells).toHaveLength(3);
    for (const cell of roomCells) {
      expect(cell.textContent).toBe('');
    }
  });

  it('renders time cells, room and track labels, and populated team cells', () => {
    const rows: SheetRow[] = [
      makeRow(),
      makeRow({Order: '2', Track: '2', 'Team#': 'CAP-102', Organization: 'Org B', NameTitle: 'CAP Team B'}),
      makeRow({Class: 'CSE', Order: '1', Track: '3', 'Team#': 'CSE-201', Organization: 'Org C', NameTitle: 'CSE Team C'}),
      makeRow({Order: '2', Track: '', 'Team#': 'SKIP-ME'}),
    ];

    const {container} = render(
      <ScheduleGrid classes={classes} rows={rows} trackInfos={trackInfos} />,
    );

    // Class titles (label + code).
    expect(screen.getByText('Capstone (CAP)')).toBeInTheDocument();
    expect(screen.getByText('Software (CSE)')).toBeInTheDocument();

    // Room headers mapped via the running class offset.
    expect(screen.getByText('Room A')).toBeInTheDocument();
    expect(screen.getByText('Room B')).toBeInTheDocument();
    expect(screen.getByText('Room C')).toBeInTheDocument();

    // Track labels.
    expect(screen.getByText('TrackA')).toBeInTheDocument();
    expect(screen.getByText('TrackB')).toBeInTheDocument();
    expect(screen.getByText('TrackC')).toBeInTheDocument();

    // Time cells computed from startTime + slotMinutes.
    expect(screen.getByText('1:00')).toBeInTheDocument();
    expect(screen.getByText('1:30')).toBeInTheDocument();
    expect(screen.getByText('2:00')).toBeInTheDocument();

    // Populated cells and organizations.
    expect(screen.getByRole('button', {name: 'CAP-101'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'CAP-102'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'CSE-201'})).toBeInTheDocument();
    expect(screen.getByText('Org A')).toBeInTheDocument();
    expect(screen.getByText('Org B')).toBeInTheDocument();
    expect(screen.getByText('Org C')).toBeInTheDocument();

    // The skipped row (empty Track) is not rendered.
    expect(screen.queryByRole('button', {name: 'SKIP-ME'})).toBeNull();

    // Cell tooltip titles.
    expect(screen.getByTitle('CAP Team A')).toBeInTheDocument();
    expect(screen.getByTitle('CAP Team B')).toBeInTheDocument();
    expect(screen.getByTitle('CSE Team C')).toBeInTheDocument();

    // CAP renders 2 orders x 2 tracks; CSE renders 1 order x 1 track.
    expect(container.querySelectorAll('.sg-td-cell')).toHaveLength(5);
  });

  it('invokes onTeamClick with the first three characters of the team number', () => {
    const onTeamClick = vi.fn();
    const rows: SheetRow[] = [
      makeRow(),
      makeRow({Class: 'CSE', Order: '1', Track: '3', 'Team#': 'CSE-201'}),
    ];

    render(
      <ScheduleGrid
        classes={classes}
        rows={rows}
        trackInfos={trackInfos}
        onTeamClick={onTeamClick}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: 'CAP-101'}));
    expect(onTeamClick).toHaveBeenCalledWith('CAP');

    fireEvent.click(screen.getByRole('button', {name: 'CSE-201'}));
    expect(onTeamClick).toHaveBeenCalledWith('CSE');
  });
});
