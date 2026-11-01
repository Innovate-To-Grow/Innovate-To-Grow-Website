import './Container.css';
import {Suspense, useEffect, useRef} from 'react';
import {Outlet, useLocation} from 'react-router';
import {LoadingIndicator} from '@/components/LoadingIndicator';
import {usePageTracking} from '@/hooks/usePageTracking';
import {notifyRouteChange} from '@/features/layout/hooks/useCurrentPathname';
import {useRouteChangeFocus} from '@/features/layout/hooks/useRouteChangeFocus';
import {useScrollResetOnNavigate} from '@/features/layout/hooks/useScrollResetOnNavigate';

/** Page shell: the 1170px content container around the routed page. */
export const Container = () => {
  usePageTracking();
  const location = useLocation();
  const mainRef = useRef<HTMLDivElement>(null);
  useScrollResetOnNavigate();
  useRouteChangeFocus(mainRef);

  // The header root lives outside the router; tell it the route changed.
  useEffect(() => {
    notifyRouteChange(location.pathname);
  }, [location.pathname]);

  return (
    <div className="app-layout container">
      <div className="app-layout-main" ref={mainRef}>
        <Suspense
          fallback={
            <div className="page-loader" role="status">
              <LoadingIndicator label="Loading…" />
            </div>
          }
        >
          <Outlet />
        </Suspense>
      </div>
    </div>
  );
};
