import {Suspense} from 'react';
import type {ComponentType, LazyExoticComponent} from 'react';
import {useLayout} from '../components/Layout/LayoutProvider/context';

interface HomepageResolverProps {
  homePage: LazyExoticComponent<ComponentType>;
  pageRegistry: Record<string, LazyExoticComponent<ComponentType> | ComponentType>;
}

export const HomepageResolver = ({homePage: HomePage, pageRegistry}: HomepageResolverProps) => {
  const {homepage_route, state} = useLayout();

  if (state === 'loading') {
    return null;
  }

  if (!homepage_route || homepage_route === '/') {
    return <HomePage />;
  }

  const PageComponent = pageRegistry[homepage_route];
  if (!PageComponent) {
    return <HomePage />;
  }

  return (
    <Suspense fallback={null}>
      <PageComponent />
    </Suspense>
  );
};
