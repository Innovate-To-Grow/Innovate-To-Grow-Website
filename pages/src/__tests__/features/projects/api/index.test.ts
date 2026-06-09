import {beforeEach, describe, expect, it, vi} from 'vitest';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
}));

const authMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  getAccessToken: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api: apiMock,
}));

vi.mock('@/features/auth', () => ({
  authApi: {
    get: authMock.get,
    post: authMock.post,
    patch: authMock.patch,
    delete: authMock.delete,
  },
  getAccessToken: authMock.getAccessToken,
}));

import {
  createPastProjectShare,
  deleteShare,
  fetchAllPastProjects,
  fetchCurrentProjects,
  fetchCurrentProjectsFull,
  fetchPastProjects,
  fetchPastProjectShare,
  fetchProjectDetail,
  listMyShares,
  scheduleProjectToGridRow,
  searchPastProjectsWithAI,
  toProjectGridRow,
  updatePastProjectShare,
  type ProjectTableRow,
} from '@/features/projects/api';
import type {ScheduleProjectRow} from '@/features/events/api';

const projectRow: ProjectTableRow = {
  id: 'p1',
  semester_label: '2026-1 Spring',
  class_code: 'ENGR 190',
  team_number: '12',
  team_name: 'Team Alpha',
  project_title: 'Better Widget',
  organization: 'UC Merced',
  industry: 'Education',
  abstract: 'Abstract',
  student_names: 'Ada, Grace',
  is_presenting: true,
  track: 1,
  presentation_order: 2,
};

describe('projects API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('maps project rows for the reusable project grid', () => {
    expect(toProjectGridRow(projectRow)).toMatchObject({
      semester_label: '2026 Spring',
      team_name: 'Team Alpha',
      is_presenting: 'Yes',
    });
    expect(toProjectGridRow({...projectRow, is_presenting: false}).is_presenting).toBe('No');
    expect(toProjectGridRow({...projectRow, is_presenting: undefined}).is_presenting).toBe('');

    const scheduleRow: ScheduleProjectRow = {
      id: 's1',
      track: 1,
      order: 1,
      year_semester: '2025-2 Fall',
      class_code: 'ENGR 191',
      team_number: '3',
      team_name: 'Schedule Team',
      project_title: 'Schedule Project',
      organization: 'Partner',
      industry: 'Robotics',
      abstract: 'Schedule abstract',
      student_names: 'Lin',
      is_presenting: false,
      tooltip: 'tip',
    };
    expect(scheduleProjectToGridRow(scheduleRow)).toMatchObject({
      semester_label: '2025 Fall',
      team_name: 'Schedule Team',
      is_presenting: 'No',
    });
  });

  it('calls public project endpoints with expected paths', async () => {
    apiMock.get.mockResolvedValue({data: {id: 'ok'}});

    await fetchCurrentProjects();
    await fetchCurrentProjectsFull();
    await fetchAllPastProjects();
    await fetchPastProjects(2, 25);
    await fetchProjectDetail('p1');

    expect(apiMock.get).toHaveBeenNthCalledWith(1, '/event/projects/');
    expect(apiMock.get).toHaveBeenNthCalledWith(2, '/event/projects/');
    expect(apiMock.get).toHaveBeenNthCalledWith(3, '/projects/past-all/');
    expect(apiMock.get).toHaveBeenNthCalledWith(4, '/projects/past/?page=2&page_size=25');
    expect(apiMock.get).toHaveBeenNthCalledWith(5, '/projects/p1/');
  });

  it('uses auth endpoints for AI search and share management', async () => {
    authMock.post.mockResolvedValue({data: {id: 'share'}});
    authMock.patch.mockResolvedValue({data: {id: 'share', name: 'Updated'}});
    authMock.get.mockResolvedValue({data: [{id: 'share'}]});
    authMock.delete.mockResolvedValue({});

    await searchPastProjectsWithAI('battery storage', 5);
    await createPastProjectShare([toProjectGridRow(projectRow)], 'Name', 'Note', 'Details');
    await updatePastProjectShare('share', {name: 'Updated', rows: [], note: '', details_text: ''});
    await listMyShares();
    await deleteShare('share');

    expect(authMock.post).toHaveBeenNthCalledWith(1, '/projects/past-ai-search/', {query: 'battery storage', limit: 5});
    expect(authMock.post).toHaveBeenNthCalledWith(2, '/projects/past-shares/', {
      rows: [toProjectGridRow(projectRow)],
      name: 'Name',
      note: 'Note',
      details_text: 'Details',
    });
    expect(authMock.patch).toHaveBeenCalledWith('/projects/past-shares/share/', {
      name: 'Updated',
      rows: [],
      note: '',
      details_text: '',
    });
    expect(authMock.get).toHaveBeenCalledWith('/projects/past-shares/mine/');
    expect(authMock.delete).toHaveBeenCalledWith('/projects/past-shares/share/');
  });

  it('fetches an authenticated share when a token exists', async () => {
    authMock.getAccessToken.mockReturnValue('token');
    authMock.get.mockResolvedValue({data: {id: 'share', can_edit: true}});

    await expect(fetchPastProjectShare('share')).resolves.toMatchObject({can_edit: true});

    expect(authMock.get).toHaveBeenCalledWith('/projects/past-shares/share/');
    expect(apiMock.get).not.toHaveBeenCalled();
  });

  it('falls back to the public share endpoint for anonymous or expired auth', async () => {
    authMock.getAccessToken.mockReturnValueOnce(null).mockReturnValueOnce('token');
    apiMock.get.mockResolvedValue({data: {id: 'share', can_edit: false}});

    await fetchPastProjectShare('share');
    expect(apiMock.get).toHaveBeenCalledWith('/projects/past-shares/share/');

    authMock.get.mockRejectedValue({response: {status: 401}});
    await fetchPastProjectShare('share');
    expect(apiMock.get).toHaveBeenCalledTimes(2);
  });

  it('rethrows non-auth share errors from the authenticated endpoint', async () => {
    authMock.getAccessToken.mockReturnValue('token');
    authMock.get.mockRejectedValue({response: {status: 500}});

    await expect(fetchPastProjectShare('share')).rejects.toMatchObject({response: {status: 500}});
  });
});
