import { useEffect, useState } from 'react';
import { fetchCMSEmbed, type CMSEmbedResponse } from '@/features/cms/api';
import {inComponentsLayer} from '@/lib/css';

// Wildcard is deliberate: the embed is designed to render inside arbitrary
// third-party pages and the payload ({type, slug, height}) is non-sensitive.
// Do not add sensitive fields to the postMessage payload without also
// narrowing `POST_TARGET` to `document.referrer`.
const POST_TARGET = '*';

/** Embed-specific body styles: transparent background, no margins. */
export const EMBED_BODY_CSS = `
      html, body {
        margin: 0 !important;
        padding: 0 !important;
        background: transparent !important;
      }
      body {
        overflow-x: hidden;
      }
    `;

/** The embeddable block for ``slug``; ``notFound`` once fetching it failed. */
export function useEmbedData(slug: string | undefined) {
  const [data, setData] = useState<CMSEmbedResponse | null>(null);
  const [notFound, setNotFound] = useState(false);
  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    fetchCMSEmbed(slug)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setNotFound(true);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);
  return { data, notFound };
}

/** A `<style id={id}>` in the document head while ``css`` is non-empty. */
export function useHeadStyle(id: string, css: string | null | undefined) {
  useEffect(() => {
    if (!css) return;
    const style = document.createElement('style');
    style.id = id;
    style.textContent = inComponentsLayer(css);
    document.head.appendChild(style);
    return () => {
      style.remove();
    };
  }, [id, css]);
}

/** `<base target="_blank">`, so block links pop out of the chromeless iframe (unless a base exists). */
export function useBaseTargetBlank() {
  useEffect(() => {
    const existing = document.head.querySelector('base');
    if (existing) return;
    const base = document.createElement('base');
    base.target = '_blank';
    document.head.appendChild(base);
    return () => {
      base.remove();
    };
  }, []);
}

/**
 * Report the page's height to the parent window (message type `i2g-embed-resize`) once ``ready``,
 * and on any size change, so the embedding iframe can fit it. A no-op outside an iframe.
 */
export function useReportHeightToParent(slug: string | undefined, ready: boolean) {
  useEffect(() => {
    if (!ready || !slug) return;
    if (window.parent === window) return; // not inside an iframe — no-op

    const reportHeight = () => {
      const height = Math.max(
        document.documentElement.scrollHeight,
        document.body ? document.body.scrollHeight : 0,
      );
      window.parent.postMessage(
        { type: 'i2g-embed-resize', slug, height },
        POST_TARGET,
      );
    };

    // Initial report + observe future changes on <html>, which reflows for
    // both content changes and container-width changes.
    reportHeight();
    const ro = new ResizeObserver(reportHeight);
    ro.observe(document.documentElement);
    window.addEventListener('load', reportHeight);
    return () => {
      ro.disconnect();
      window.removeEventListener('load', reportHeight);
    };
  }, [ready, slug]);
}
