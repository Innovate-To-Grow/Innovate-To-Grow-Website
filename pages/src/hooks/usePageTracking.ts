import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { trackPageView } from '../services/api/analytics';

export const usePageTracking = () => {
  const location = useLocation();
  const prevPath = useRef<string | null>(null);

  useEffect(() => {
    const currentPath = location.pathname;

    // Avoid duplicate tracking for the same path
    if (currentPath === prevPath.current) return;
    prevPath.current = currentPath;

    trackPageView({
      path: currentPath,
      referrer: document.referrer,
    });
  }, [location.pathname]);
};
