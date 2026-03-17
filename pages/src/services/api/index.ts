// Barrel export - re-exports everything so external imports remain unchanged.
// Usage: import { type MenuItem } from '../../services/api';
//        import api from '../../services/api';

export { default } from './client';
export { api } from './client';

export type {
  FooterLink,
  FooterCTAButton,
  FooterColumn,
  FooterSocialLink,
  FooterContentData,
  FooterContentResponse,
  MenuItem,
  Menu,
  LayoutData,
} from './layout';
export { fetchLayoutData, clearLayoutCache } from './layout';

export type { HealthCheckResponse, HealthStatus } from './health';
export { checkHealth, bypassMaintenance } from './health';

export type { PaginatedResponse } from './types';

export type { NewsArticle } from './news';
export { fetchNews, fetchLatestNews, fetchNewsDetail } from './news';

export type { ProjectSummary, ProjectDetail, ProjectTableRow, SemesterWithProjects, SemesterWithFullProjects } from './projects';
export { fetchCurrentProjects, fetchCurrentProjectsFull, fetchAllPastProjects, fetchPastProjects, fetchProjectDetail } from './projects';
