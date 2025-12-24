import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import './index.css';
import { router } from './router';
import { Footer } from './components/Footer/Footer';
import { MainMenu } from './components/MainMenu/MainMenu';
import { HealthCheckProvider } from './components/HealthCheck/HealthCheckProvider';

// Mount main app to #root with health check
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HealthCheckProvider pollingInterval={10000}>
      <RouterProvider router={router} />
    </HealthCheckProvider>
  </StrictMode>,
);

// Mount MainMenu to #menu-root
const menuRoot = document.getElementById('menu-root');
if (menuRoot) {
  createRoot(menuRoot).render(
    <StrictMode>
      <MainMenu />
    </StrictMode>,
  );
}

// Mount footer to #footer-root
const footerRoot = document.getElementById('footer-root');
if (footerRoot) {
  createRoot(footerRoot).render(
    <StrictMode>
      <Footer />
    </StrictMode>,
  );
}
