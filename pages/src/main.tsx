import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import './index.css';
import { router } from './router';
import { Footer, MainMenu, LayoutProvider } from './components/Layout';
import { HealthCheckProvider } from './components/MaintenanceMode';
import { AuthProvider } from './components/Auth';
import { ErrorBoundary } from './components/ErrorBoundary';

// Mount main app to #root with health check and auth
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <HealthCheckProvider pollingInterval={10000}>
        <AuthProvider>
          <LayoutProvider>
            <RouterProvider router={router} />
          </LayoutProvider>
        </AuthProvider>
      </HealthCheckProvider>
    </ErrorBoundary>
  </StrictMode>,
);

// Skip menu and footer for isolated iframe routes (admin preview + public embed widget)
const _path = window.location.pathname;
const isBlockPreview = _path === '/_block-preview' || _path.startsWith('/_embed/');

// Mount MainMenu to #menu-root with AuthProvider and LayoutProvider
// No BrowserRouter needed — MainMenu uses router.navigate() directly, not <Link> or router hooks
const menuRoot = document.getElementById('menu-root');
if (menuRoot && !isBlockPreview) {
  createRoot(menuRoot).render(
    <StrictMode>
      <ErrorBoundary>
        <AuthProvider>
          <LayoutProvider>
            <MainMenu />
          </LayoutProvider>
        </AuthProvider>
      </ErrorBoundary>
    </StrictMode>,
  );
}

// Mount footer to #footer-root with LayoutProvider
const footerRoot = document.getElementById('footer-root');
if (footerRoot && !isBlockPreview) {
  createRoot(footerRoot).render(
    <StrictMode>
      <ErrorBoundary>
        <LayoutProvider>
          <Footer />
        </LayoutProvider>
      </ErrorBoundary>
    </StrictMode>,
  );
}
