import type {EventSchedulePayload, ScheduleProjectRow, ScheduleSlot} from '@/features/events/api';

/**
 * A trimmed copy of the production GET /api/event/schedule/ payload (Spring 2026: two slots of CAP track 1, one of
 * CSE track 6 and one team that is not presenting, abstracts shortened), keeping its shape:
 *
 * - `projects[].id` of a presenting team is its schedule SLOT id, not a project id;
 * - the slot's `project_id` is the event CurrentProject id, which is what Current Projects links to;
 * - teams that are not presenting are listed at track 0 by their CurrentProject id, with no `year_semester`;
 * - none of these ids is an archive Project id: GET /api/projects/<id>/ answers 404 for every one of them
 *   (the archive copy of "ASHRAE HVAC Design Calculations" is ARCHIVE_PROJECT_ID).
 */
export const HVAC_SLOT_ID = '0ef6b199-6fb0-4d9d-9e95-11b5d6f0006c';
export const HVAC_PROJECT_ID = '2280fa08-f914-45fe-8a62-905b2d68e0df';
export const WEED_SLOT_ID = 'ed45c3f3-9c9d-4885-95bd-dadc13210654';
export const WEED_PROJECT_ID = '07f64b8b-732a-4b23-bba1-38542d5f9b58';
export const DASHBOARD_SLOT_ID = 'a82c31e5-88d3-4cd6-8ad5-82b2f1b9bc40';
export const DASHBOARD_PROJECT_ID = '7db11209-2213-4f3f-b856-dada52abe7b7';
/** Not presenting: listed at track 0 by its CurrentProject id. */
export const WING_PROJECT_ID = 'cbea890e-224f-4fb8-b358-1e1f5ee288eb';
/** The archive Project row with the same title as HVAC_PROJECT_ID: a different id. */
export const ARCHIVE_PROJECT_ID = '5970763b-cf7c-40d6-a87c-96916e0ea695';

const HVAC_ABSTRACT =
  'This project aimed to design a complete HVAC system with appropriate heating and cooling for a multi - use - University Building in Denver, Colorado.';
const WEED_ABSTRACT =
  'Hunt Farms is a family owned farm that has operated for generations. As water efficiency and sustainable agriculture have become more important in California, James Hunt began exploring alternative crops for part of the farm.';

const slot = (overrides: Partial<ScheduleSlot>): ScheduleSlot => ({
  id: '',
  order: 1,
  is_break: false,
  display_text: '',
  team_number: '',
  team_name: '',
  project_title: '',
  organization: '',
  industry: '',
  abstract: '',
  student_names: '',
  tooltip: '',
  project_id: null,
  ...overrides,
});

const presentingRow = (
  current: ScheduleSlot,
  track: number,
  classCode: string,
): ScheduleProjectRow => ({
  id: current.id,
  track,
  order: current.order,
  year_semester: '2026-1 Spring',
  class_code: classCode,
  team_number: current.team_number,
  team_name: current.team_name,
  project_title: current.project_title,
  organization: current.organization,
  industry: current.industry,
  abstract: current.abstract,
  student_names: current.student_names,
  is_presenting: true,
  tooltip: current.tooltip,
});

const hvacSlot = slot({
  id: HVAC_SLOT_ID,
  order: 1,
  display_text: '101',
  team_number: '101',
  team_name: 'HVAC Regulators',
  project_title: 'ASHRAE HVAC Design Calculations',
  organization: 'ASHRAE - Sierra Delta',
  industry: 'Energy',
  abstract: HVAC_ABSTRACT,
  student_names: 'Brian Arroyo, Joel Gonzalez, Kyle On, Manuel Cruz Cavero',
  tooltip: 'Team: HVAC Regulators  -  Project: ASHRAE HVAC Design Calculations',
  project_id: HVAC_PROJECT_ID,
});

const weedSlot = slot({
  id: WEED_SLOT_ID,
  order: 2,
  display_text: '108',
  team_number: '108',
  team_name: 'Burn to Bloom',
  project_title: 'Propane-Powered See-and-Flame Weed Control System for Organic Agave Using the Farm‑NG Amiga Platform',
  organization: 'Hunt Farms',
  industry: 'Agriculture',
  abstract: WEED_ABSTRACT,
  student_names: 'Aleksandris Brainerd, Ian Barry-Smith, Jeremy Wu, Larry San',
  tooltip: 'Team: Burn to Bloom  -  Project: Propane-Powered See-and-Flame Weed Control System for Organic Agave Using the Farm‑NG Amiga Platform',
  project_id: WEED_PROJECT_ID,
});

const dashboardSlot = slot({
  id: DASHBOARD_SLOT_ID,
  order: 1,
  display_text: '336',
  team_number: '336',
  team_name: 'The SustainaBros.',
  project_title: 'Sustainability Dashboard',
  organization: 'UC Merced Sustainability Office',
  industry: 'Education',
  abstract: 'The Office of Sustainability leads award-winning climate action initiatives for UC Merced.',
  student_names: 'Brian Huynh, Steven Murillo, Isaac Jee, Javon Hudgins, Julian Olaviano',
  tooltip: 'Team: The SustainaBros.  -  Project: Sustainability Dashboard',
  project_id: DASHBOARD_PROJECT_ID,
});

export const currentSchedulePayload = (): EventSchedulePayload => ({
  // Production sends only {id, name} here.
  event: {id: '64d87471-dcd2-474d-a705-b0e63d7a32e9', name: '2026 Spring I2G Event'} as EventSchedulePayload['event'],
  show_winners: true,
  grand_winners: [{section: 'CAP', winner: 'CAP-104: MillGuard Systems'}],
  expo: {title: 'EXPO: POSTERS AND DEMOS', location: 'Gym (only, NO Zoom)', items: []},
  presentations_title: 'PRESENTATIONS',
  sections: [
    {
      id: '57f55878-a96d-4b7d-b59c-dfabc2fdc638',
      code: 'CAP',
      label: 'Engineering Capstone',
      display_order: 0,
      start_time: '1:00',
      slot_minutes: 30,
      accent_color: '#002856',
      max_order: 5,
      tracks: [
        {
          id: '27af1c24-9f01-46f6-8eda-1a7e2b0564bf',
          track_number: 1,
          label: 'Track 1',
          room: 'Glacier 165',
          zoom_link: '',
          topic: 'Gases',
          winner: '',
          display_order: 0,
          slots: [hvacSlot, weedSlot],
        },
      ],
    },
    {
      id: '3555cdd7-ee78-40cc-8802-ccc42b4b9535',
      code: 'CSE',
      label: 'Software Engineering Capstone',
      display_order: 2,
      start_time: '1:00',
      slot_minutes: 20,
      accent_color: '#FFBF3C',
      max_order: 9,
      tracks: [
        {
          id: 'ffada354-2842-4b22-a0d3-90e6d9fdd0d6',
          track_number: 6,
          label: 'Track 6',
          room: 'Glacier 140',
          zoom_link: '',
          topic: 'Ada Lovelace',
          winner: '',
          display_order: 0,
          slots: [dashboardSlot],
        },
      ],
    },
  ],
  awards: {title: 'AWARDS & RECEPTION', location: 'Gym', items: []},
  projects: [
    presentingRow(hvacSlot, 1, 'CAP'),
    presentingRow(weedSlot, 1, 'CAP'),
    presentingRow(dashboardSlot, 6, 'CSE'),
    {
      id: WING_PROJECT_ID,
      track: 0,
      order: 0,
      year_semester: '',
      class_code: 'CAP',
      team_number: '201',
      team_name: 'CAP-201',
      project_title: 'Distributed-Flapping Wing with Glide-Lock Mechanism',
      organization: 'UCM Aerospace',
      industry: 'AeroSpace',
      abstract: 'Abstract-201',
      student_names: '',
      is_presenting: false,
      tooltip: '',
    },
  ],
});
