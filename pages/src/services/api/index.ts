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
export {
  fetchLayoutData,
  clearLayoutCache,
  readLayoutCache,
  writeLayoutCache,
  LAYOUT_CACHE_VERSION,
} from './layout';

export type { HealthCheckResponse, HealthStatus } from './health';
export { checkHealth, bypassMaintenance } from './health';

export type { PaginatedResponse } from './types';

export type { NewsArticle } from './news';
export { fetchNews, fetchLatestNews, fetchNewsDetail } from './news';

export type {
  PastProjectShare,
  ProjectDetail,
  ProjectGridRow,
  ProjectSummary,
  ProjectTableRow,
  SemesterWithFullProjects,
  SemesterWithProjects,
} from './projects';
export {
  createPastProjectShare,
  fetchAllPastProjects,
  fetchCurrentProjects,
  fetchCurrentProjectsFull,
  fetchPastProjectShare,
  fetchPastProjects,
  fetchProjectDetail,
  toProjectGridRow,
} from './projects';

export type { TicketOption, QuestionOption, Registration, RegistrationEvent, RegistrationTicket, RegistrationAnswer, EventRegistrationOptions } from './events';
export { fetchRegistrationOptions, createRegistration, fetchMyTickets, resendTicketEmail } from './events';
