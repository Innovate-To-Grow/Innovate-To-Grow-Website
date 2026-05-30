import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { router } from '@/app/router';
import { Footer, MainMenu, LayoutProvider } from '@/features/layout';
import { HealthCheckProvider } from '@/app/MaintenanceMode';
import { AuthProvider } from '@/features/auth';
import { ErrorBoundary } from '@/app/ErrorBoundary';
import {
  SECTION_TITLES_KEY,
  buildHiddenSectionsCss,
  isTruthyParam,
  normalizeHiddenSections,
  parseHiddenSectionsParam,
} from '@/features/cms/components/hiddenSections';

function injectIsolatedHiddenSections(searchParams: URLSearchParams) {
  const hiddenSections = normalizeHiddenSections([
    ...parseHiddenSectionsParam(searchParams.get('hide-sections')),
    ...(isTruthyParam(searchParams.get('hide-titles')) ? [SECTION_TITLES_KEY] : []),
  ]);
  const css = buildHiddenSectionsCss(hiddenSections);
  if (!css) return;
  const style = document.createElement('style');
  style.id = 'itg-isolated-hide-sections';
  style.textContent = css;
  document.head.appendChild(style);
}

export function mountApp() {
  const _path = window.location.pathname;
  const _searchParams = new URLSearchParams(window.location.search);
  const _isolatedFlag = _searchParams.has('_isolated');
  const isBlockPreview = _path === '/_block-preview' || _path.startsWith('/_embed/') || _isolatedFlag;

  if (_isolatedFlag) {
    injectIsolatedHiddenSections(_searchParams);
  }

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
}
