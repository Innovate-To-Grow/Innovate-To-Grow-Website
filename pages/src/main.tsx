import './index.css';
import {captureAuthCallbackParams} from '@/features/auth/api/callbackParams';

// Capture one-time credentials before importing the application providers.
// The provider graph creates the browser router at module evaluation time, so
// importing it statically would let the router retain the pre-scrub URL and a
// legacy alias redirect could put a query token back into the address bar.
captureAuthCallbackParams();

async function bootstrap() {
  const [
    {mountApp},
    {
      loadFontAwesomeStylesheet,
      loadThirdPartyScripts,
      markIsolatedIframeRoute,
    },
  ] = await Promise.all([
    import('@/app/providers'),
    import('@/app/thirdPartyLoaders'),
  ]);

  markIsolatedIframeRoute();
  loadFontAwesomeStylesheet();
  mountApp();
  loadThirdPartyScripts();
}

void bootstrap();
