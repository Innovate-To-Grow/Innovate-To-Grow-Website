// Barrel export - re-exports everything so external imports remain unchanged.
// Usage: import { fetchPageContent, type PageContent } from '../../services/api';
//        import api from '../../services/api';

export { default } from './client';
export { api } from './client';

export type { PageContent, GoogleSheetDataResponse, HomeContent } from './pages';
export { fetchPageContent, fetchHomeContent, fetchGoogleSheetData } from './pages';

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

export type { HealthCheckResponse } from './health';
export { checkHealth } from './health';

export type { PreviewTokenValidationResponse, PreviewDataResponse } from './preview';
export { validatePreviewToken, fetchPreviewData } from './preview';
