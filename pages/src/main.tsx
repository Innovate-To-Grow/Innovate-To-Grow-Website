import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import './index.css';
import { router } from './router';
import { Footer, MainMenu, LayoutProvider } from './components/Layout';
import { HealthCheckProvider } from './components/MaintenanceMode';

// Mount main app to #root with health check
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HealthCheckProvider pollingInterval={10000}>
      <RouterProvider router={router} />
    </HealthCheckProvider>
  </StrictMode>,
);

// Mount MainMenu to #menu-root with LayoutProvider
const menuRoot = document.getElementById('menu-root');
if (menuRoot) {
  createRoot(menuRoot).render(
    <StrictMode>
      <LayoutProvider>
        <MainMenu />
      </LayoutProvider>
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
