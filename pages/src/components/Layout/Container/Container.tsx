import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import './Container.css';

export const Container = () => {
  return (
    <div className="app-layout container">
      <Suspense fallback={<div className="page-loader">Loading...</div>}>
        <Outlet />
      </Suspense>
    </div>
  );
};
