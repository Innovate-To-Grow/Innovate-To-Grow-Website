import type {EventConfig} from './types';

export const configsFrom2025To2024: Record<string, EventConfig> = {
  '2025-fall': {
    title: 'Fall 2025 Event',
    semester: 'Fall 2025',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 2, orderCount: 6, startTime: '1:00', slotMinutes: 30, trackLabels: ['AgTech', 'FoodTech']},
      {code: 'CEE', label: 'Civil & Environmental Engineering', trackCount: 1, orderCount: 4, startTime: '1:00', slotMinutes: 30, trackLabels: ['Environment']},
      {code: 'CSE', label: 'Software Engineering Capstone', trackCount: 2, orderCount: 10, startTime: '1:00', slotMinutes: 20, trackLabels: ['Tim Berners-Lee', 'Grace Hopper'], accentColor: '#FFBF3C'},
    ],
  },
  '2025-spring': {
    title: 'Spring 2025 Event',
    semester: 'Spring 2025',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 3, orderCount: 7, startTime: '1:00', slotMinutes: 30, trackLabels: ['AgTech', 'FoodTech', 'Precision']},
      {code: 'CEE', label: 'Civil & Environmental Engineering', trackCount: 1, orderCount: 7, startTime: '1:00', slotMinutes: 30, trackLabels: ['Environment']},
      {code: 'CSE', label: 'Software Engineering Capstone', trackCount: 4, orderCount: 10, startTime: '1:00', slotMinutes: 20, trackLabels: ['Alan Turing', 'Ada Lovelace', 'John von Neumann', 'Joan Clarke'], accentColor: '#FFBF3C'},
    ],
  },
  '2024-fall': {
    title: 'Fall 2024 Event',
    semester: 'Fall 2024',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 3, orderCount: 5, startTime: '1:00', slotMinutes: 30, trackLabels: ['AgTech', 'FoodTech', 'Precision']},
      {code: 'CEE', label: 'Civil & Environmental Engineering', trackCount: 1, orderCount: 4, startTime: '1:00', slotMinutes: 30, trackLabels: ['Environment']},
      {code: 'CSE', label: 'Software Engineering Capstone', trackCount: 3, orderCount: 7, startTime: '1:00', slotMinutes: 20, trackLabels: ['Ag-Food', 'Data', 'Industry'], accentColor: '#FFBF3C'},
    ],
  },
  '2024-spring': {
    title: 'Spring 2024 Event',
    semester: 'Spring 2024',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 5, orderCount: 6, startTime: '1:00', slotMinutes: 30, trackLabels: ['Devices', 'Precision', 'AgTech', 'Lab', 'FoodTech']},
      {code: 'CSE', label: 'Software Engineering Capstone', trackCount: 3, orderCount: 9, startTime: '1:00', slotMinutes: 20, trackLabels: ['Ag-Food', 'Data', 'Industry'], accentColor: '#FFBF3C'},
    ],
  },
};
