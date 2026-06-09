import {describe, expect, it} from 'vitest';

import {toProjectGridRow, type ProjectTableRow} from './index';

describe('project api row mappers', () => {
  it('preserves the project id when mapping past projects into grid rows', () => {
    const project: ProjectTableRow = {
      id: '11111111-1111-4111-8111-111111111111',
      semester_label: '2025 Spring',
      class_code: 'CAP',
      team_number: '101',
      team_name: 'General Rotary',
      project_title: 'Rotary Joint Testing System',
      organization: 'E&J Gallo Winery',
      industry: 'Food Processing',
      abstract: 'A detailed abstract.',
      student_names: 'Alice, Bob',
      is_presenting: false,
      track: null,
      presentation_order: null,
    };

    expect(toProjectGridRow(project)).toMatchObject({
      id: project.id,
      project_title: project.project_title,
      is_presenting: 'No',
    });
  });
});
