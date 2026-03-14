import {Suspense} from 'react';
import type {ComponentType, LazyExoticComponent} from 'react';
import {useLayout} from '../components/Layout/LayoutProvider/context';

interface HomepageResolverProps {
  pageRegistry: Record<string, LazyExoticComponent<ComponentType> | ComponentType>;
}

export const HomepageResolver = ({pageRegistry}: HomepageResolverProps) => {
  const {homepage_route, state} = useLayout();

  if (state === 'loading') {
    return null;
  }

  const route = homepage_route || '/';
  const PageComponent = pageRegistry[route];
  if (!PageComponent) {
    // Fallback to root CMS page if configured route not found
    const RootPage = pageRegistry['/'];
    if (RootPage) {
      return (
        <Suspense fallback={null}>
          <RootPage />
        </Suspense>
      );
    }
    return null;
  }

  return (
    <Suspense fallback={null}>
      <PageComponent />
    </Suspense>
  );
};
