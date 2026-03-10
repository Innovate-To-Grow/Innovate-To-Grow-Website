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

export type {
  Presentation,
  Track,
  Program,
  TrackWinner,
  SpecialAward,
  ExpoRow,
  ReceptionRow,
  EventData,
} from './events';
export { fetchEvent } from './events';

export type { HealthCheckResponse, HealthStatus } from './health';
export { checkHealth } from './health';

export type { NewsArticle, PaginatedResponse } from './news';
export { fetchNews, fetchLatestNews, fetchNewsDetail } from './news';

export type { ProjectSummary, ProjectDetail, SemesterWithProjects } from './projects';
export { fetchCurrentProjects, fetchPastProjects, fetchProjectDetail } from './projects';
