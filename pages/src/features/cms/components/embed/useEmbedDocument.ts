import { useEffect, useState } from 'react';
import { fetchCMSEmbed, type CMSEmbedResponse } from '@/features/cms/api';
import {inComponentsLayer} from '@/lib/css';

// Wildcard is deliberate: the embed is designed to render inside arbitrary
// third-party pages and the payload ({type, slug, height}) is non-sensitive.
// Do not add sensitive fields to the postMessage payload without also
// narrowing `POST_TARGET` to `document.referrer`.
const POST_TARGET = '*';

/** Embed-specific body styles: no margins, and the page background ``background``. */
const embedBodyCss = (background: string) => `
      html, body {
        margin: 0 !important;
        padding: 0 !important;
        background: ${background} !important;
      }
      body {
        overflow-x: hidden;
      }
    `;

/** Block widgets are transparent, so their blocks sit on the host page like its own content. */
export const EMBED_BODY_CSS = embedBodyCss('transparent');

/**
 * App-route widgets are whole site pages, whose text colours and striped rows assume the site's page
 * background; on a coloured host page a transparent one would leave them unreadable. So they keep it, with
 * padding inside the frame (16px; at 768px and below 20px, the phone page gutter): the controls never touch
 * the iframe's edge, and the background reads as a card around the widget. Block widgets get neither.
 */
export const EMBED_APP_ROUTE_BODY_CSS = `${embedBodyCss('var(--itg-color-bg-page, #fff)')}
      .cms-embed-app-route {
        box-sizing: border-box;
        padding: 16px;
      }
      @media (max-width: 768px) {
        .cms-embed-app-route {
          padding: 20px;
        }
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
      // The height of the <html> box, which wraps the content (index.html makes the isolated roots
      // plain blocks). Not scrollHeight: that never drops below the frame's own height, which is
      // the height last reported, so the frame could grow but never shrink back.
      const height = Math.ceil(document.documentElement.getBoundingClientRect().height);
      // Nothing has rendered yet (an app-route page still loading its code): keep the frame's height
      // rather than collapse it to nothing for a moment. Snippets pasted earlier copy any height.
      if (height <= 0) return;
      window.parent.postMessage(
        { type: 'i2g-embed-resize', slug, height },
        POST_TARGET,
      );
    };

    // Initial report + observe future changes on <html>, which resizes for
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
