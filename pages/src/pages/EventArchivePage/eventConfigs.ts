import type {ClassConfig} from '../../components/ScheduleGrid';

export interface EventConfig {
  title: string;
  semester: string;
  classes: ClassConfig[];
}

/**
 * Presentation layout configuration for archived I2G events.
 *
 * Sheet data (spreadsheet IDs, ranges, tracks) is now managed in the
 * backend via GoogleSheetSource and served at /api/sheets/<slug>/.
 * This file retains only the class/schedule layout config used by
 * the ScheduleGrid component.
 */
export const EVENT_CONFIGS: Record<string, EventConfig> = {
  // ── Fall 2025 ────────────────────────────────────────────────────────
  '2025-fall': {
    title: 'Fall 2025 Event',
    semester: 'Fall 2025',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 2,
        orderCount: 6,
        startTime: '1:00',
        slotMinutes: 30,
        trackLabels: ['AgTech', 'FoodTech'],
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
    ],
  },

  // ── Spring 2025 ────────────────────────────────────────────────────
  '2025-spring': {
    title: 'Spring 2025 Event',
    semester: 'Spring 2025',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 3,
        orderCount: 7,
        startTime: '1:00',
        slotMinutes: 30,
        trackLabels: ['AgTech', 'FoodTech', 'Precision'],
      },
      {
        code: 'CEE',
        label: 'Civil & Environmental Engineering',
        trackCount: 1,
        orderCount: 7,
        startTime: '1:00',
        slotMinutes: 30,
        trackLabels: ['Environment'],
      },
      {
        code: 'CSE',
        label: 'Software Engineering Capstone',
        trackCount: 4,
        orderCount: 10,
        startTime: '1:00',
        slotMinutes: 20,
        trackLabels: ['Alan Turing', 'Ada Lovelace', 'John von Neumann', 'Joan Clarke'],
        accentColor: '#FFBF3C',
      },
    ],
  },

  // ── Fall 2024 ────────────────────────────────────────────────────────
  '2024-fall': {
    title: 'Fall 2024 Event',
    semester: 'Fall 2024',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 3,
        orderCount: 5,
        startTime: '1:00',
        slotMinutes: 30,
        trackLabels: ['AgTech', 'FoodTech', 'Precision'],
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
        trackCount: 3,
        orderCount: 7,
        startTime: '1:00',
        slotMinutes: 20,
        trackLabels: ['Ag-Food', 'Data', 'Industry'],
        accentColor: '#FFBF3C',
      },
    ],
  },

  // ── Spring 2024 ────────────────────────────────────────────────────
  '2024-spring': {
    title: 'Spring 2024 Event',
    semester: 'Spring 2024',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 5,
        orderCount: 6,
        startTime: '1:00',
        slotMinutes: 30,
        trackLabels: ['Devices', 'Precision', 'AgTech', 'Lab', 'FoodTech'],
      },
      {
        code: 'CSE',
        label: 'Software Engineering Capstone',
        trackCount: 3,
        orderCount: 9,
        startTime: '1:00',
        slotMinutes: 20,
        trackLabels: ['Ag-Food', 'Data', 'Industry'],
        accentColor: '#FFBF3C',
      },
    ],
  },

  // ── Fall 2023 ────────────────────────────────────────────────────────
  '2023-fall': {
    title: 'Fall 2023 Event',
    semester: 'Fall 2023',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 3,
        orderCount: 6,
        startTime: '2:00',
        slotMinutes: 30,
        trackLabels: ['AgTech', 'FoodTech', 'Precision'],
      },
      {
        code: 'CEE',
        label: 'Civil & Environmental Engineering',
        trackCount: 1,
        orderCount: 5,
        startTime: '2:00',
        slotMinutes: 30,
        trackLabels: ['Environment'],
      },
      {
        code: 'CSE',
        label: 'Software Engineering Capstone',
        trackCount: 2,
        orderCount: 8,
        startTime: '2:00',
        slotMinutes: 20,
        trackLabels: ['Ag-Food', 'Data'],
        accentColor: '#FFBF3C',
      },
    ],
  },

  // ── Spring 2023 ────────────────────────────────────────────────────
  '2023-spring': {
    title: 'Spring 2023 Event',
    semester: 'Spring 2023',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 5,
        orderCount: 6,
        startTime: '2:00',
        slotMinutes: 30,
        trackLabels: ['Health', 'Mechanics', 'AgTech', 'Precision', 'Food'],
      },
      {
        code: 'CEE',
        label: 'Civil & Environmental Engineering',
        trackCount: 1,
        orderCount: 4,
        startTime: '2:00',
        slotMinutes: 30,
        trackLabels: ['Environment'],
      },
      {
        code: 'CSE',
        label: 'Software Engineering Capstone',
        trackCount: 3,
        orderCount: 8,
        startTime: '2:00',
        slotMinutes: 20,
        trackLabels: ['Ag-Food', 'Data', 'Industry'],
        accentColor: '#FFBF3C',
      },
    ],
  },

  // ── Fall 2022 ────────────────────────────────────────────────────────
  '2022-fall': {
    title: 'Fall 2022 Event',
    semester: 'Fall 2022',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 2,
        orderCount: 6,
        startTime: '12:30',
        slotMinutes: 30,
        trackLabels: ['AgTech', 'FoodTech'],
      },
      {
        code: 'CEE',
        label: 'Civil & Environmental Engineering',
        trackCount: 1,
        orderCount: 2,
        startTime: '12:30',
        slotMinutes: 30,
        trackLabels: ['Environment'],
      },
      {
        code: 'CSE',
        label: 'Software Engineering Capstone',
        trackCount: 2,
        orderCount: 9,
        startTime: '12:30',
        slotMinutes: 20,
        trackLabels: ['Ag-Food', 'Data'],
        accentColor: '#FFBF3C',
      },
    ],
  },

  // ── Spring 2022 ────────────────────────────────────────────────────
  '2022-spring': {
    title: 'Spring 2022 Event',
    semester: 'Spring 2022',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 5,
        orderCount: 6,
        startTime: '1:00',
        slotMinutes: 30,
        trackLabels: ['AgTech', 'Process', 'Safety', 'System', 'Waste'],
      },
      {
        code: 'CEE',
        label: 'Civil & Environmental Engineering',
        trackCount: 1,
        orderCount: 2,
        startTime: '1:00',
        slotMinutes: 30,
        trackLabels: ['Environment'],
      },
      {
        code: 'CSE',
        label: 'Software Engineering Capstone',
        trackCount: 4,
        orderCount: 8,
        startTime: '1:00',
        slotMinutes: 20,
        trackLabels: ['Code', 'Computer', 'Data', 'User'],
        accentColor: '#FFBF3C',
      },
    ],
  },

  // ── Fall 2021 ────────────────────────────────────────────────────────
  '2021-fall': {
    title: 'Fall 2021 Event',
    semester: 'Fall 2021',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 6,
        orderCount: 6,
        startTime: '1:00',
        slotMinutes: 30,
        trackLabels: ['AgEngineering', 'AgTech', 'FoodTech', 'System', 'TomatoTech', 'Transportation'],
      },
      {
        code: 'CEE',
        label: 'Civil & Environmental Engineering',
        trackCount: 1,
        orderCount: 2,
        startTime: '1:00',
        slotMinutes: 30,
        trackLabels: ['Environment'],
      },
      {
        code: 'CSE',
        label: 'Software Engineering Capstone',
        trackCount: 4,
        orderCount: 8,
        startTime: '1:00',
        slotMinutes: 20,
        trackLabels: ['Code', 'Computer', 'Data', 'User'],
        accentColor: '#FFBF3C',
      },
    ],
  },

  // ── Spring 2021 ────────────────────────────────────────────────────
  '2021-spring': {
    title: 'Spring 2021 Event',
    semester: 'Spring 2021',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 6,
        orderCount: 6,
        startTime: '11:00',
        slotMinutes: 30,
        trackLabels: ['AgEng', 'AgTech', 'Materials', 'Process', 'Tomato', 'Transportation'],
      },
      {
        code: 'EngSL',
        label: 'Engineering Service Learning',
        trackCount: 1,
        orderCount: 2,
        startTime: '11:00',
        slotMinutes: 30,
        trackLabels: ['Non-Profits'],
      },
    ],
  },

  // ── Fall 2020 ────────────────────────────────────────────────────────
  '2020-fall': {
    title: 'Fall 2020 Event',
    semester: 'Fall 2020',
    classes: [
      {
        code: 'CAP',
        label: 'Engineering Capstone',
        trackCount: 4,
        orderCount: 6,
        startTime: '1:00',
        slotMinutes: 30,
        trackLabels: ['AgTech', 'Food Processing', 'New Products', 'Energy'],
      },
    ],
  },
};
