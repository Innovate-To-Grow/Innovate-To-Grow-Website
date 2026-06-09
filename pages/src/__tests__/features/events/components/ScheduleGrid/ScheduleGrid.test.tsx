import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {ScheduleGrid, type ClassConfig} from '@/features/events/components/ScheduleGrid/ScheduleGrid';
import type {SheetRow, TrackInfo} from '@/components/ui/SheetsDataTable';

const classes: ClassConfig[] = [
  {
    code: 'CSE',
    label: 'Computer Science',
    trackCount: 2,
    orderCount: 2,
    startTime: '1:00',
    slotMinutes: 30,
    trackLabels: ['Software', 'Systems'],
    accentColor: '#0055aa',
  },
];

const rows: SheetRow[] = [
  {
    Track: '1',
    Order: '1',
    'Year-Semester': '2026 Spring',
    Class: 'CSE',
    'Team#': '101A',
    TeamName: 'Team One',
    'Project Title': 'Schedule Builder',
    Organization: 'UC Merced',
    Industry: 'Education',
    Abstract: '',
    'Student Names': '',
    'Showcase Participation': 'Yes',
    NameTitle: 'Team One title',
  },
  {
    Track: '2',
    Order: '2',
    'Year-Semester': '2026 Spring',
    Class: 'CSE',
    'Team#': '202B',
    TeamName: 'Team Two',
    'Project Title': 'Track Builder',
    Organization: 'Lab',
    Industry: 'Research',
    Abstract: '',
    'Student Names': '',
    'Showcase Participation': 'Yes',
    NameTitle: 'Team Two title',
  },
];

const trackInfos: TrackInfo[] = [
  {name: 'Software', room: 'Room 101', zoomLink: ''},
  {name: 'Systems', room: 'Room 102', zoomLink: ''},
];

describe('ScheduleGrid', () => {
  it('renders loading and error states', () => {
    const loading = render(<ScheduleGrid classes={classes} rows={[]} trackInfos={[]} loading />);
    expect(screen.getByText('Loading schedule...')).toBeInTheDocument();
    loading.unmount();

    render(<ScheduleGrid classes={classes} rows={[]} trackInfos={[]} error="Schedule failed" />);
    expect(screen.getByText('Schedule failed')).toBeInTheDocument();
  });

  it('maps rows into class, time, and track cells and forwards team clicks', () => {
    const onTeamClick = vi.fn();

    render(
      <ScheduleGrid
        classes={classes}
        rows={[...rows, {...rows[0], Track: '', Order: ''}]}
        trackInfos={trackInfos}
        onTeamClick={onTeamClick}
      />,
    );

    expect(screen.getByText('Computer Science (CSE)')).toBeInTheDocument();
    expect(screen.getByText('Room 101')).toBeInTheDocument();
    expect(screen.getByText('Room 102')).toBeInTheDocument();
    expect(screen.getByText('1:00')).toBeInTheDocument();
    expect(screen.getByText('1:30')).toBeInTheDocument();
    expect(screen.getByText('UC Merced')).toBeInTheDocument();
    expect(screen.getByText('Lab')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: '101A'}));
    expect(onTeamClick).toHaveBeenCalledWith('101');
  });
});
