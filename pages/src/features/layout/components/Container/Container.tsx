import { Suspense } from 'react';
import { Outlet } from 'react-router';
import { usePageTracking } from '@/hooks/usePageTracking';

export const Container = () => {
  usePageTracking();

  return (
    <div className="app-layout container">
      <Suspense fallback={<div className="page-loader">Loading...</div>}>
        <Outlet />
      </Suspense>
    </div>
  );
};
