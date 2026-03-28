import type {EventConfig} from './types';

export const configsFrom2021To2020: Record<string, EventConfig> = {
  '2021-fall': {
    title: 'Fall 2021 Event',
    semester: 'Fall 2021',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 6, orderCount: 6, startTime: '1:00', slotMinutes: 30, trackLabels: ['AgEngineering', 'AgTech', 'FoodTech', 'System', 'TomatoTech', 'Transportation']},
      {code: 'CEE', label: 'Civil & Environmental Engineering', trackCount: 1, orderCount: 2, startTime: '1:00', slotMinutes: 30, trackLabels: ['Environment']},
      {code: 'CSE', label: 'Software Engineering Capstone', trackCount: 4, orderCount: 8, startTime: '1:00', slotMinutes: 20, trackLabels: ['Code', 'Computer', 'Data', 'User'], accentColor: '#FFBF3C'},
    ],
  },
  '2021-spring': {
    title: 'Spring 2021 Event',
    semester: 'Spring 2021',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 6, orderCount: 6, startTime: '11:00', slotMinutes: 30, trackLabels: ['AgEng', 'AgTech', 'Materials', 'Process', 'Tomato', 'Transportation']},
      {code: 'EngSL', label: 'Engineering Service Learning', trackCount: 1, orderCount: 2, startTime: '11:00', slotMinutes: 30, trackLabels: ['Non-Profits']},
    ],
  },
  '2020-fall': {
    title: 'Fall 2020 Event',
    semester: 'Fall 2020',
    classes: [
      {code: 'CAP', label: 'Engineering Capstone', trackCount: 4, orderCount: 6, startTime: '1:00', slotMinutes: 30, trackLabels: ['AgTech', 'Food Processing', 'New Products', 'Energy']},
    ],
  },
};
