import type {EventSchedulePayload, ScheduleProjectRow, ScheduleSlot} from '@/features/events/api';

export function slot(order: number, teamNumber: string): ScheduleSlot {
  return {
    id: `${teamNumber}-${order}`,
    order,
    is_break: false,
    display_text: teamNumber,
    team_number: teamNumber,
    team_name: '',
    project_title: '',
    organization: '',
    industry: '',
    abstract: '',
    student_names: '',
    tooltip: '',
    project_id: null,
  };
}

function breakSlot(order: number, trackId: string): ScheduleSlot {
  return {
    id: `break-${trackId}-${order}`,
    order,
    is_break: true,
    display_text: 'Break',
    team_number: '',
    team_name: '',
    project_title: '',
    organization: '',
    industry: '',
    abstract: '',
    student_names: '',
    tooltip: '',
    project_id: null,
  };
}

export function schedulePayload(): EventSchedulePayload {
  return {
    event: {
      id: 'schedule-1',
      name: 'Demo Day',
      slug: 'demo-day',
      date: 'May 7, 2026',
      location: 'Conference Center',
      description: 'Presentation schedule',
    },
    show_winners: false,
    grand_winners: [],
    expo: {
      title: 'Expo',
      location: '',
      items: [],
    },
    presentations_title: 'PRESENTATIONS',
    sections: [
      {
        id: 'section-cse',
        code: 'CSE',
        label: 'Computer Science',
        display_order: 1,
        start_time: '1:00',
        slot_minutes: 30,
        accent_color: '#002856',
        max_order: 4,
        tracks: [
          {
            id: 'track-1',
            track_number: 1,
            label: 'Track 1',
            room: 'Room 101',
            zoom_link: '',
            topic: 'Software',
            winner: '',
            display_order: 1,
            slots: [slot(1, 'CSE-101'), breakSlot(2, 'track-1'), slot(3, 'CSE-103')],
          },
          {
            id: 'track-2',
            track_number: 2,
            label: 'Track 2',
            room: 'Room 102',
            zoom_link: '',
            topic: 'Systems',
            winner: '',
            display_order: 2,
            slots: [slot(1, 'CSE-201'), breakSlot(2, 'track-2')],
          },
        ],
      },
    ],
    awards: {
      title: 'Awards',
      location: '',
      items: [],
    },
    projects: [],
  };
}

export function projectRow(overrides: Partial<ScheduleProjectRow> = {}): ScheduleProjectRow {
  return {
    id: 'project-1',
    track: 1,
    order: 1,
    year_semester: '2026 Spring',
    class_code: 'CSE',
    team_number: 'CSE-101',
    team_name: 'Team Alpha',
    project_title: 'Smart Grid',
    organization: 'Acme',
    industry: 'Energy',
    abstract: 'A smart grid project.',
    student_names: 'Alice, Bob',
    is_presenting: true,
    tooltip: '',
    ...overrides,
  };
}
