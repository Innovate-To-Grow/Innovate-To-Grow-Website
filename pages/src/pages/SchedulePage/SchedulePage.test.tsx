import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SchedulePage} from './SchedulePage';

vi.mock('../../features/events/useCurrentEventSchedule', () => ({
  useCurrentEventSchedule: vi.fn(() => ({
    loading: false,
    error: null,
    data: {
      event: {
        id: 'event-1',
        name: 'Spring Showcase',
        slug: 'spring-showcase',
        date: '2026-05-01',
        location: 'Conference Center',
        description: 'Schedule details for the current showcase.',
      },
      expo: {
        title: 'EXPO: POSTERS AND DEMOS',
        location: 'Gym',
        items: [
          {
            id: 'expo-1',
            time: '9:00',
            title: 'Registration and Coffee',
            location: 'Gym',
          },
        ],
      },
      presentations_title: 'PRESENTATIONS',
      sections: [
        {
          id: 'section-cap',
          code: 'CAP',
          label: 'Engineering Capstone',
          display_order: 0,
          start_time: '1:00',
          slot_minutes: 30,
          accent_color: '#002856',
          max_order: 1,
          tracks: [
            {
              id: 'track-1',
              track_number: 1,
              label: 'Track 1',
              room: 'Granite',
              zoom_link: '',
              topic: 'FoodTech',
              display_order: 0,
              slots: [
                {
                  id: 'slot-1',
                  order: 1,
                  is_break: false,
                  display_text: 'CAP-101',
                  team_number: 'CAP-101',
                  team_name: 'Alpha',
                  project_title: 'Smart Farm',
                  organization: 'Agri Corp',
                  industry: 'Ag',
                  abstract: 'A smart farming project.',
                  student_names: 'Ada, Ben',
                  tooltip: 'Mentor - Lead',
                  project_id: null,
                },
              ],
            },
          ],
        },
      ],
      awards: {
        title: 'AWARDS & RECEPTION',
        location: 'Gym',
        items: [
          {
            id: 'award-1',
            time: '4:45',
            title: 'Award Ceremony',
            location: 'Gym',
          },
        ],
      },
      projects: [
        {
          id: 'project-1',
          track: 1,
          order: 1,
          year_semester: '2026-1 Spring',
          class_code: 'CAP',
          team_number: 'CAP-101',
          team_name: 'Alpha',
          project_title: 'Smart Farm',
          organization: 'Agri Corp',
          industry: 'Ag',
          abstract: 'A smart farming project.',
          student_names: 'Ada, Ben',
          tooltip: 'Mentor - Lead',
        },
      ],
    },
  })),
}));

describe('SchedulePage', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders agenda blocks, presentations, and projects table', () => {
    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {name: 'Spring Showcase'})).toBeInTheDocument();
    expect(screen.getByText('EXPO: POSTERS AND DEMOS')).toBeInTheDocument();
    expect(screen.getByText('PRESENTATIONS')).toBeInTheDocument();
    expect(screen.getByText('AWARDS & RECEPTION')).toBeInTheDocument();
    expect(screen.getByDisplayValue('')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'CAP-101'})).toBeInTheDocument();
  });

  it('uses team clicks to seed the project search field', () => {
    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'CAP-101'}));

    expect(screen.getByDisplayValue('CAP-101')).toBeInTheDocument();
  });
});
