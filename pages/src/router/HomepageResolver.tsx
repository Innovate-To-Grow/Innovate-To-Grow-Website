import {useLayout} from '../components/Layout/LayoutProvider/context';
import {CMSPageComponent} from '@/features/cms';

export const HomepageResolver = () => {
  const {homepage_route, state} = useLayout();

  if (state === 'loading') {
    return null;
  }

  return <CMSPageComponent routeOverride={homepage_route || '/'} />;
};
