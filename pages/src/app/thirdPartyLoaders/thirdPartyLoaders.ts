import {isIsolatedRoute} from '@/lib/isolatedRoute';

const USERWAY_SCRIPT_ID = 'i2g-userway-loader';
const SITEIMPROVE_SCRIPT_ID = 'i2g-siteimprove-loader';

export function markIsolatedIframeRoute(pathname = window.location.pathname, search = window.location.search): void {
  if (isIsolatedRoute(pathname, search)) {
    document.documentElement.dataset.blockPreview = '';
  }
}

function appendScript(
  id: string,
  src: string,
  attributes: Readonly<Record<string, string>> = {},
): void {
  if (document.getElementById(id)) return;

  const script = document.createElement('script');
  script.id = id;
  script.src = src;
  script.async = true;
  for (const [name, value] of Object.entries(attributes)) {
    script.setAttribute(name, value);
  }
  (document.body || document.head).appendChild(script);
}

export function loadThirdPartyScripts(pathname = window.location.pathname, search = window.location.search): void {
  if (isIsolatedRoute(pathname, search)) return;

  appendScript(USERWAY_SCRIPT_ID, 'https://cdn.userway.org/widget.js', {
    'data-account': '6Uvgvyrrph',
  });

  const loadSiteImprove = () => {
    if (isIsolatedRoute(window.location.pathname, window.location.search)) return;
    appendScript(
      SITEIMPROVE_SCRIPT_ID,
      'https://siteimproveanalytics.com/js/siteanalyze_8343.js',
    );
  };
  const schedule = () => {
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(loadSiteImprove, {timeout: 3000});
    } else {
      globalThis.setTimeout(loadSiteImprove, 1500);
    }
  };
  if (document.readyState === 'complete') schedule();
  else window.addEventListener('load', schedule, {once: true});
}
