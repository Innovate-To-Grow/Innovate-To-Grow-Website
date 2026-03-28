import api from './client';
import authApi from '../auth';
import type { PaginatedResponse } from './types';

export type { PaginatedResponse } from './types';

export interface ProjectSummary {
  id: string;
  project_title: string;
  team_name: string;
  organization: string;
  industry: string;
  class_code: string;
}

export interface ProjectTableRow {
  id: string;
  semester_label: string;
  class_code: string;
  team_number: string;
  team_name: string;
  project_title: string;
  organization: string;
  industry: string;
  abstract: string;
  student_names: string;
  track: number | null;
  presentation_order: number | null;
}

export interface ProjectGridRow {
  semester_label: string;
  class_code: string;
  team_number: string;
  team_name: string;
  project_title: string;
  organization: string;
  industry: string;
  abstract: string;
  student_names: string;
}

export interface ProjectDetail {
  id: string;
  project_title: string;
  team_name: string;
  team_number: string;
  organization: string;
  industry: string;
  abstract: string;
  student_names: string;
  class_code: string;
  track: number | null;
  presentation_order: number | null;
  semester_label: string;
}

export interface SemesterWithProjects {
  id: string;
  year: number;
  season: number;
  label: string;
  projects: ProjectSummary[];
}

export interface SemesterWithFullProjects {
  id: string;
  year: number;
  season: number;
  label: string;
  projects: ProjectTableRow[];
}

export interface PastProjectShare {
  id: string;
  rows: ProjectGridRow[];
  share_url: string;
  created_at: string;
}

export const toProjectGridRow = (project: ProjectTableRow): ProjectGridRow => ({
  semester_label: project.semester_label,
  class_code: project.class_code,
  team_number: project.team_number,
  team_name: project.team_name,
  project_title: project.project_title,
  organization: project.organization,
  industry: project.industry,
  abstract: project.abstract,
  student_names: project.student_names,
});

export const fetchCurrentProjects = async (): Promise<SemesterWithProjects> => {
  const response = await api.get<SemesterWithProjects>('/projects/current/');
  return response.data;
};

export const fetchCurrentProjectsFull = async (): Promise<SemesterWithFullProjects> => {
  const response = await api.get<SemesterWithFullProjects>('/projects/current/');
  return response.data;
};

export const fetchAllPastProjects = async (): Promise<ProjectTableRow[]> => {
  const response = await api.get<ProjectTableRow[]>('/projects/past-all/');
  return response.data;
};

export const fetchPastProjects = async (
  page = 1,
  pageSize = 5
): Promise<PaginatedResponse<SemesterWithProjects>> => {
  const response = await api.get<PaginatedResponse<SemesterWithProjects>>(
    `/projects/past/?page=${page}&page_size=${pageSize}`
  );
  return response.data;
};

export const fetchProjectDetail = async (id: string): Promise<ProjectDetail> => {
  const response = await api.get<ProjectDetail>(`/projects/${id}/`);
  return response.data;
};

export const createPastProjectShare = async (rows: ProjectGridRow[]): Promise<PastProjectShare> => {
  const response = await api.post<PastProjectShare>('/projects/past-shares/', {rows});
  return response.data;
};

export const fetchPastProjectShare = async (id: string): Promise<PastProjectShare> => {
  const response = await api.get<PastProjectShare>(`/projects/past-shares/${id}/`);
  return response.data;
};

// ======================== Import ========================

export interface ImportStats {
  semesters_created: number;
  semesters_existing: number;
  projects_created: number;
  projects_updated: number;
  rows_skipped: number;
}

export const importProjectsFromExcel = async (file: File): Promise<ImportStats> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await authApi.post<ImportStats>('/projects/import/', formData);
  return response.data;
};

export const downloadImportTemplate = async (): Promise<void> => {
  const response = await authApi.get('/projects/import/template/', {
    responseType: 'blob',
  });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'project_import_template.xlsx';
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};
