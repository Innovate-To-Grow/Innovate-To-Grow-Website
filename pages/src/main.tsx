import './styles/layers.css';
import './index.css';
import {captureAuthCallbackParams} from '@/features/auth/api/callbackParams';
import {mountApp} from '@/app/providers';
import {installPreloadErrorRecovery} from '@/app/pageReload';
import {
  loadThirdPartyScripts,
  markIsolatedIframeRoute,
} from '@/app/thirdPartyLoaders';

// Capture one-time credentials before router creation. mountApp creates the
// router only after this synchronous URL scrub has completed.
captureAuthCallbackParams();
// A route chunk that fails to load (deleted by a deploy since this tab opened) reloads onto the new build
// from the route error screen; this lets a stylesheet that fails through, so the chunk's script decides.
installPreloadErrorRecovery();

function bootstrap() {
  markIsolatedIframeRoute();
  mountApp();
  loadThirdPartyScripts();
}

bootstrap();
