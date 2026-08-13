import './index.css';
import {captureAuthCallbackParams} from '@/features/auth/api/callbackParams';
import {mountApp} from '@/app/providers';
import {
  loadThirdPartyScripts,
  markIsolatedIframeRoute,
} from '@/app/thirdPartyLoaders';

// Capture one-time credentials before router creation. mountApp creates the
// router only after this synchronous URL scrub has completed.
captureAuthCallbackParams();

function bootstrap() {
  markIsolatedIframeRoute();
  mountApp();
  loadThirdPartyScripts();
}

bootstrap();
