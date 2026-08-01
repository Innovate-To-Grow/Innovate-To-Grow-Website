import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
} from 'react';
import DOMPurify from 'dompurify';
import {fetchCMSEmbedHosts} from '@/features/cms/api';

const SANITIZE_OPTIONS = {
  USE_PROFILES: {html: true},
  ADD_TAGS: ['iframe'],
  ADD_ATTR: ['target', 'rel', 'aria-label', 'allow', 'allowfullscreen', 'frameborder'],
};

interface EmbedHostSnapshot {
  ready: boolean;
  hosts: readonly string[];
  revision: string;
}

const INITIAL_EMBED_HOST_SNAPSHOT: EmbedHostSnapshot = {
  ready: false,
  hosts: [],
  revision: '',
};

let embedHostSnapshot = INITIAL_EMBED_HOST_SNAPSHOT;
let embedHostRequestStarted = false;
const embedHostListeners = new Set<() => void>();

const notifyEmbedHostListeners = () => {
  for (const listener of embedHostListeners) listener();
};

const normalizeHostEntries = (hosts: unknown): string[] => {
  if (!Array.isArray(hosts)) return [];
  return [
    ...new Set(
      hosts
        .filter((host): host is string => typeof host === 'string')
        .map((host) => host.trim().toLowerCase())
        .filter(Boolean),
    ),
  ];
};

const ensureEmbedHostsLoaded = () => {
  if (embedHostRequestStarted) return;
  embedHostRequestStarted = true;
  void fetchCMSEmbedHosts()
    .then((response) => {
      embedHostSnapshot = {
        ready: true,
        hosts: normalizeHostEntries(response.hosts),
        revision:
          typeof response.revision === 'string' ? response.revision : '',
      };
    })
    .catch(() => {
      // Fail closed. Public rich text remains visible, but no iframe is ever
      // admitted when the allowlist cannot be established.
      embedHostSnapshot = {
        ready: true,
        hosts: [],
        revision: '',
      };
    })
    .finally(notifyEmbedHostListeners);
};

const subscribeToEmbedHosts = (listener: () => void) => {
  embedHostListeners.add(listener);
  return () => embedHostListeners.delete(listener);
};

const getEmbedHostSnapshot = () => embedHostSnapshot;

const isAllowedEmbedHost = (
  hostname: string,
  allowedHosts: readonly string[],
) => {
  const normalizedHost = hostname.toLowerCase();
  return allowedHosts.some((entry) => {
    if (entry.startsWith('*.')) {
      const base = entry.slice(2);
      // Match the backend exactly: a wildcard covers subdomains only. The apex
      // must be listed separately.
      return Boolean(base) && normalizedHost.endsWith(`.${base}`);
    }
    return normalizedHost === entry;
  });
};

const stripDisallowedIframes = (
  sanitizedHtml: string,
  allowedHosts: readonly string[],
) => {
  const template = document.createElement('template');
  template.innerHTML = sanitizedHtml;
  for (const iframe of template.content.querySelectorAll('iframe')) {
    const src = iframe.getAttribute('src') ?? '';
    try {
      const url = new URL(src);
      if (
        url.protocol !== 'https:' ||
        !isAllowedEmbedHost(url.hostname, allowedHosts)
      ) {
        iframe.remove();
      }
    } catch {
      iframe.remove();
    }
  }
  return template.innerHTML;
};

interface SafeHtmlProps {
  html: string;
  className?: string;
}

export const SafeHtml = memo(({html, className}: SafeHtmlProps) => {
  const ref = useRef<HTMLDivElement>(null);
  const embedHosts = useSyncExternalStore(
    subscribeToEmbedHosts,
    getEmbedHostSnapshot,
    getEmbedHostSnapshot,
  );
  const containsIframe = /<iframe(?:\s|>)/i.test(html);

  useEffect(() => {
    if (containsIframe) ensureEmbedHostsLoaded();
  }, [containsIframe]);

  const sanitizedHtml = useMemo(
    () =>
      stripDisallowedIframes(
        DOMPurify.sanitize(html, SANITIZE_OPTIONS),
        embedHosts.ready ? embedHosts.hosts : [],
      ),
    [embedHosts, html],
  );

  // Set innerHTML via ref so the DOM (including iframes) is only replaced
  // when the sanitized HTML actually changes — not on every parent re-render.
  useEffect(() => {
    if (ref.current) {
      ref.current.innerHTML = sanitizedHtml;
    }
  }, [sanitizedHtml]);

  return <div ref={ref} className={className} />;
});
