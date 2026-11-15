import type {
  PastProjectAISearchResponse,
  ProjectDetail,
  ProjectTableRow,
} from '../../src/features/projects/api';

// Project ids are UUIDs: the project page treats anything else in its URL as no project at all.
const E2E_PROJECT_IDS = ['e2e00000-0000-4000-8000-000000000001', 'e2e00000-0000-4000-8000-000000000002'] as const;

export function pastProjectRows(): ProjectTableRow[] {
  return [
    {
      id: E2E_PROJECT_IDS[0],
      semester_label: '2025 Fall',
      class_code: 'CSE 120',
      team_number: '7',
      team_name: 'Team Helix',
      project_title: 'Adaptive Irrigation Dashboard',
      organization: 'Acme Corp',
      industry: 'Agriculture',
      abstract: 'A dashboard that optimizes irrigation schedules.',
      student_names: 'Ada Lovelace, Alan Turing',
      is_presenting: true,
      track: 1,
      presentation_order: 3,
    },
    {
      id: E2E_PROJECT_IDS[1],
      semester_label: '2025 Spring',
      class_code: 'ME 140',
      team_number: '2',
      team_name: 'Team Vortex',
      project_title: 'Low-Cost Wind Turbine',
      organization: 'Globex',
      industry: 'Energy',
      abstract: 'A low-cost residential wind turbine prototype.',
      student_names: 'Grace Hopper, Edsger Dijkstra',
      is_presenting: false,
      track: null,
      presentation_order: null,
    },
  ];
}

// CurrentProject ids: /projects/all/ lists the active schedule's teams by them, and /projects/<id>/ answers for them.
const E2E_CURRENT_PROJECT_IDS = ['e2e00000-0000-4000-8000-0000000000c1', 'e2e00000-0000-4000-8000-0000000000c2'] as const;

/**
 * What `/projects/all/` lists (mockAllProjects), in its order: the active schedule's teams first, in team order (one
 * the schedule only lists, with the sheet's placeholder team name and abstract as stored, then a presenting one),
 * then the archive (pastProjectRows).
 */
export function allProjectRows(): ProjectTableRow[] {
  return [
    {
      id: E2E_CURRENT_PROJECT_IDS[0],
      semester_label: '2026-2 Fall',
      class_code: 'CAP',
      team_number: '102',
      team_name: 'CAP-102',
      project_title: 'Packing Line Sorter',
      organization: 'Valley Foods',
      industry: 'Food Processing',
      abstract: 'Abstract-102',
      student_names: 'Mary Jackson',
      is_presenting: false,
      track: null,
      presentation_order: null,
      catalog: 'current',
    },
    {
      id: E2E_CURRENT_PROJECT_IDS[1],
      semester_label: '2026-2 Fall',
      class_code: 'CAP',
      team_number: '201',
      team_name: 'Team Kestrel',
      project_title: 'Orchard Soil Moisture Network',
      organization: 'UC Merced Farm',
      industry: 'Agriculture',
      abstract: 'Wireless probes that report soil moisture across the campus almond groves.',
      student_names: 'Katherine Johnson, Dorothy Vaughan',
      is_presenting: true,
      track: 1,
      presentation_order: 1,
      catalog: 'current',
    },
    ...pastProjectRows(),
  ];
}

export function projectDetail(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    id: E2E_PROJECT_IDS[0],
    project_title: 'Adaptive Irrigation Dashboard',
    team_name: 'Team Helix',
    team_number: '7',
    organization: 'Acme Corp',
    industry: 'Agriculture',
    abstract: 'A dashboard that optimizes irrigation schedules using live sensor data.',
    student_names: 'Ada Lovelace, Alan Turing',
    class_code: 'CSE 120',
    track: 1,
    presentation_order: 3,
    semester_label: '2025 Fall',
    ...overrides,
  };
}

// -- AI search -----------------------------------------------------------

export function aiSearchResponse(
  overrides: Partial<PastProjectAISearchResponse> = {},
): PastProjectAISearchResponse {
  return {
    available: true,
    query: 'irrigation',
    results: [pastProjectRows()[0]],
    usage: {inputTokens: 100, outputTokens: 50, totalTokens: 150},
    ...overrides,
  };
}
