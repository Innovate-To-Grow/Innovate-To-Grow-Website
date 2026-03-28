// Barrel export - re-exports everything so external imports remain unchanged.
// Usage: import { type MenuItem } from '../../services/api';
//        import api from '../../services/api';

export { default } from '../../shared/api/client';
export { api } from '../../shared/api/client';

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
} from '../../features/layout/api';
export {
  fetchLayoutData,
  clearLayoutCache,
  readLayoutCache,
  writeLayoutCache,
  LAYOUT_CACHE_VERSION,
} from '../../features/layout/api';

export type { HealthCheckResponse, HealthStatus } from './health';
export { checkHealth, bypassMaintenance } from './health';

export type { PaginatedResponse } from '../../shared/api/types';

export type { NewsArticle } from '../../features/news/api';
export { fetchNews, fetchLatestNews, fetchNewsDetail } from '../../features/news/api';

export type {
  PastProjectShare,
  ProjectDetail,
  ProjectGridRow,
  ProjectSummary,
  ProjectTableRow,
  SemesterWithFullProjects,
  SemesterWithProjects,
} from '../../features/projects/api';
export {
  createPastProjectShare,
  fetchAllPastProjects,
  fetchCurrentProjects,
  fetchCurrentProjectsFull,
  fetchPastProjectShare,
  fetchPastProjects,
  fetchProjectDetail,
  toProjectGridRow,
} from '../../features/projects/api';

export type {
  TicketOption,
  QuestionOption,
  Registration,
  RegistrationEvent,
  RegistrationTicket,
  RegistrationAnswer,
  EventRegistrationOptions,
} from '../../features/events/api';
export {
  fetchRegistrationOptions,
  createRegistration,
  fetchMyTickets,
  resendTicketEmail,
} from '../../features/events/api';
