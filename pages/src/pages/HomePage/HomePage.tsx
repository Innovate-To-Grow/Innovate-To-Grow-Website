import {CMSPageComponent} from '../../components/CMS';
import {useLayout} from '../../components/Layout';

export const HomePage = () => {
  const {homepage_route, state} = useLayout();

  if (state === 'loading') {
    return null;
  }

  return <CMSPageComponent routeOverride={homepage_route || '/'} />;
};
