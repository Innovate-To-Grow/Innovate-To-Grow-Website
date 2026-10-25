import './Container.css';
import {Suspense, useEffect} from 'react';
import {Outlet, useLocation} from 'react-router';
import {usePageTracking} from '@/hooks/usePageTracking';
import {notifyRouteChange} from '@/features/layout/hooks/useCurrentPathname';

/** Page shell: the 1170px content container around the routed page. */
export const Container = () => {
  usePageTracking();
  const location = useLocation();

  // The header root lives outside the router; tell it the route changed.
  useEffect(() => {
    notifyRouteChange(location.pathname);
  }, [location.pathname]);

  return (
    <div className="app-layout container">
      <div className="app-layout-main">
        <Suspense fallback={<div className="page-loader">Loading...</div>}>
          <Outlet />
        </Suspense>
      </div>
    </div>
  );
};
