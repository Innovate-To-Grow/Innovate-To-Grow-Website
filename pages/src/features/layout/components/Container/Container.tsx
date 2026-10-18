import {Suspense, useEffect, useMemo} from 'react';
import {Outlet, useLocation} from 'react-router';
import {usePageTracking} from '@/hooks/usePageTracking';
import {notifyRouteChange} from '@/features/layout/hooks/useCurrentPathname';
import {allowsSectionNav, resolveSection} from '@/features/layout/sections';
import {useMenu} from '../LayoutProvider/context';
import {SectionNav, SectionSelect} from '../SectionNav/SectionNav';

/**
 * Page shell: the 1170px content container with, when the page belongs to a
 * CMS menu section that has children, the section sidebar (desktop) or the
 * "In <Section>" select (phone) next to / above the routed page.
 */
export const Container = () => {
  usePageTracking();
  const location = useLocation();
  const {menu} = useMenu();

  // The header root lives outside the router; tell it the route changed.
  useEffect(() => {
    notifyRouteChange(location.pathname);
  }, [location.pathname]);

  const match = useMemo(() => {
    if (!allowsSectionNav(location.pathname, location.search)) return null;
    const resolved = resolveSection(menu?.items, location.pathname);
    return resolved.section ? resolved : null;
  }, [menu, location.pathname, location.search]);

  const section = match?.section ?? null;

  return (
    <div className={`app-layout container${section ? ' has-section-nav' : ''}`}>
      {section && match ? <SectionNav section={section} current={match} /> : null}
      <div className="app-layout-main">
        {section && match ? <SectionSelect section={section} current={match} /> : null}
        <Suspense fallback={<div className="page-loader">Loading...</div>}>
          <Outlet />
        </Suspense>
      </div>
    </div>
  );
};
