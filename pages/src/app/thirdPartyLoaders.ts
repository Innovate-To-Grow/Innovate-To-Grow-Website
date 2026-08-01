const ISOLATED_ROUTE_PREFIX = '/_embed/';
const FONT_AWESOME_STYLESHEET_ID = 'i2g-font-awesome-stylesheet';
const FONT_AWESOME_STYLESHEET_HREF =
  '/static/vendor/font-awesome/4.7.0/css/font-awesome.min.css';
const USERWAY_SCRIPT_ID = 'i2g-userway-loader';
const SITEIMPROVE_SCRIPT_ID = 'i2g-siteimprove-loader';

/**
 * Load the first-party Font Awesome stylesheet without blocking the HTML
 * parser. Keeping this in the Vite bundle avoids an inline-script CSP
 * exception while preserving the previous preload-then-stylesheet behavior.
 */
export function loadFontAwesomeStylesheet(): void {
  if (document.getElementById(FONT_AWESOME_STYLESHEET_ID)) return;

  const link = document.createElement('link');
  link.id = FONT_AWESOME_STYLESHEET_ID;
  link.rel = 'preload';
  link.as = 'style';
  link.href = FONT_AWESOME_STYLESHEET_HREF;
  link.onload = () => {
    link.onload = null;
    link.rel = 'stylesheet';
  };
  document.head.appendChild(link);
}

export function markIsolatedIframeRoute(pathname = window.location.pathname): void {
  if (pathname === '/_block-preview' || pathname.startsWith(ISOLATED_ROUTE_PREFIX)) {
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

export function loadThirdPartyScripts(pathname = window.location.pathname): void {
  if (pathname === '/_block-preview' || pathname.startsWith(ISOLATED_ROUTE_PREFIX)) {
    return;
  }

  appendScript(USERWAY_SCRIPT_ID, 'https://cdn.userway.org/widget.js', {
    'data-account': '6Uvgvyrrph',
  });
  appendScript(
    SITEIMPROVE_SCRIPT_ID,
    'https://siteimproveanalytics.com/js/siteanalyze_8343.js',
  );
}
