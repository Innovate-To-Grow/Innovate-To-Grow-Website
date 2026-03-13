import type {ClassConfig} from '../components/ScheduleGrid';

/**
 * Shared schedule class configurations used by HomePage and SchedulePage.
 * Each entry defines a class section in the event schedule grid.
 */
export const SCHEDULE_CLASS_CONFIGS: ClassConfig[] = [
  {
    code: 'CAP',
    label: 'Engineering Capstone',
    trackCount: 2,
    orderCount: 6,
    startTime: '1:00',
    slotMinutes: 30,
    trackLabels: ['FoodTech', 'Precision'],
  },
  {
    code: 'CEE',
    label: 'Civil & Environmental Engineering',
    trackCount: 1,
    orderCount: 4,
    startTime: '1:00',
    slotMinutes: 30,
    trackLabels: ['Environment'],
  },
  {
    code: 'CSE',
    label: 'Software Engineering Capstone',
    trackCount: 2,
    orderCount: 10,
    startTime: '1:00',
    slotMinutes: 20,
    trackLabels: ['Tim Berners-Lee', 'Grace Hopper'],
    accentColor: '#FFBF3C',
  },
];
