import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import './index.css';
import { router } from './router';
import { Footer, MainMenu, LayoutProvider } from './components/Layout';
import { HealthCheckProvider } from './components/MaintenanceMode';
import { AuthProvider } from './components/Auth';

// Mount main app to #root with health check and auth
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HealthCheckProvider pollingInterval={10000}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </HealthCheckProvider>
  </StrictMode>,
);

// Mount MainMenu to #menu-root with AuthProvider and LayoutProvider
// No BrowserRouter needed — MainMenu uses router.navigate() directly, not <Link> or router hooks
const menuRoot = document.getElementById('menu-root');
if (menuRoot) {
  createRoot(menuRoot).render(
    <StrictMode>
      <AuthProvider>
        <LayoutProvider>
          <MainMenu />
        </LayoutProvider>
      </AuthProvider>
    </StrictMode>,
  );
}

// Mount footer to #footer-root with LayoutProvider
const footerRoot = document.getElementById('footer-root');
if (footerRoot) {
  createRoot(footerRoot).render(
    <StrictMode>
      <LayoutProvider>
        <Footer />
      </LayoutProvider>
    </StrictMode>,
  );
}
