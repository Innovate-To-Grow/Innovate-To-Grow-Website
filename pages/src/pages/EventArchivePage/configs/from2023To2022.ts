import type {EventConfig} from './types';

export const configsFrom2023To2022: Record<string, EventConfig> = {
  '2023-fall': {
    title: 'Fall 2023 Event',
    semester: 'Fall 2023',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 3, orderCount: 6, startTime: '2:00', slotMinutes: 30, trackLabels: ['AgTech', 'FoodTech', 'Precision']},
      {code: 'CEE', label: 'Civil & Environmental Engineering', trackCount: 1, orderCount: 5, startTime: '2:00', slotMinutes: 30, trackLabels: ['Environment']},
      {code: 'CSE', label: 'Software Engineering Capstone', trackCount: 2, orderCount: 8, startTime: '2:00', slotMinutes: 20, trackLabels: ['Ag-Food', 'Data'], accentColor: '#FFBF3C'},
    ],
  },
  '2023-spring': {
    title: 'Spring 2023 Event',
    semester: 'Spring 2023',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 5, orderCount: 6, startTime: '2:00', slotMinutes: 30, trackLabels: ['Health', 'Mechanics', 'AgTech', 'Precision', 'Food']},
      {code: 'CEE', label: 'Civil & Environmental Engineering', trackCount: 1, orderCount: 4, startTime: '2:00', slotMinutes: 30, trackLabels: ['Environment']},
      {code: 'CSE', label: 'Software Engineering Capstone', trackCount: 3, orderCount: 8, startTime: '2:00', slotMinutes: 20, trackLabels: ['Ag-Food', 'Data', 'Industry'], accentColor: '#FFBF3C'},
    ],
  },
  '2022-fall': {
    title: 'Fall 2022 Event',
    semester: 'Fall 2022',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 2, orderCount: 6, startTime: '12:30', slotMinutes: 30, trackLabels: ['AgTech', 'FoodTech']},
      {code: 'CEE', label: 'Civil & Environmental Engineering', trackCount: 1, orderCount: 2, startTime: '12:30', slotMinutes: 30, trackLabels: ['Environment']},
      {code: 'CSE', label: 'Software Engineering Capstone', trackCount: 2, orderCount: 9, startTime: '12:30', slotMinutes: 20, trackLabels: ['Ag-Food', 'Data'], accentColor: '#FFBF3C'},
    ],
  },
  '2022-spring': {
    title: 'Spring 2022 Event',
    semester: 'Spring 2022',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 5, orderCount: 6, startTime: '1:00', slotMinutes: 30, trackLabels: ['AgTech', 'Process', 'Safety', 'System', 'Waste']},
      {code: 'CEE', label: 'Civil & Environmental Engineering', trackCount: 1, orderCount: 2, startTime: '1:00', slotMinutes: 30, trackLabels: ['Environment']},
      {code: 'CSE', label: 'Software Engineering Capstone', trackCount: 4, orderCount: 8, startTime: '1:00', slotMinutes: 20, trackLabels: ['Code', 'Computer', 'Data', 'User'], accentColor: '#FFBF3C'},
    ],
  },
};
