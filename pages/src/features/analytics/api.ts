import api from '../../shared/api/client';

interface PageViewPayload {
  path: string;
  referrer: string;
}

export const trackPageView = async (payload: PageViewPayload): Promise<void> => {
  try {
    await api.post('/analytics/pageview/', payload);
  } catch {
    // Silently fail — tracking should never break the user experience
  }
};
