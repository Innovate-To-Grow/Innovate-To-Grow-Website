import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { BlockRenderer } from './BlockRenderer';
import { fetchCMSEmbed, type CMSEmbedResponse } from '../../features/cms/api';

/**
 * Public embed page rendered inside a third-party iframe.
 *
 * - Fetches a single embeddable block by slug from /cms/embed/<slug>/.
 * - Renders it inside the correct `page_css_class` wrapper so block styles
 *   (which cascade from `.cms-page ...` selectors) apply.
 * - Injects page_css scoped to the page.
 * - Reports its own height to the parent window via postMessage so the iframe
 *   can auto-resize (message type `i2g-embed-resize`).
 * - Adds <base target="_blank"> so any internal links open in a new window,
 *   preventing users from getting stuck in the chromeless iframe view.
 */

// Wildcard is deliberate: the embed is designed to render inside arbitrary
// third-party pages and the payload ({type, slug, height}) is non-sensitive.
// Do not add sensitive fields to the postMessage payload without also
// narrowing `POST_TARGET` to `document.referrer`.
const POST_TARGET = '*';

export const EmbedBlockPage = () => {
  const { embedSlug } = useParams<{ embedSlug: string }>();
  const [data, setData] = useState<CMSEmbedResponse | null>(null);
  const [notFound, setNotFound] = useState(false);

  // Fetch block data
  useEffect(() => {
    if (!embedSlug) return;
    let cancelled = false;
    fetchCMSEmbed(embedSlug)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setNotFound(true);
      });
    return () => {
      cancelled = true;
    };
  }, [embedSlug]);

  // Inject <base target="_blank"> so block links pop out of the iframe
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

  // Inject embed-specific body styles (transparent background, no margins)
  useEffect(() => {
    const style = document.createElement('style');
    style.id = 'itg-embed-body';
    style.textContent = `
      html, body {
        margin: 0 !important;
        padding: 0 !important;
        background: transparent !important;
      }
      body {
        overflow-x: hidden;
      }
    `;
    document.head.appendChild(style);
    return () => {
      style.remove();
    };
  }, []);

  // Inject page_css (from the parent CMS page)
  useEffect(() => {
    if (!data?.page_css) return;
    const style = document.createElement('style');
    style.id = 'itg-embed-page-css';
    style.textContent = data.page_css;
    document.head.appendChild(style);
    return () => {
      style.remove();
    };
  }, [data?.page_css]);

  // Report height to parent (once data is rendered, and on any size change)
  useEffect(() => {
    if (!data || !embedSlug) return;
    if (window.parent === window) return; // not inside an iframe — no-op

    const reportHeight = () => {
      const height = Math.max(
        document.documentElement.scrollHeight,
        document.body ? document.body.scrollHeight : 0,
      );
      window.parent.postMessage(
        { type: 'i2g-embed-resize', slug: embedSlug, height },
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
  }, [data, embedSlug]);

  const containerRef = useRef<HTMLDivElement>(null);

  if (notFound || !embedSlug) {
    return (
      <div style={{ padding: '24px', color: '#6b7280', fontFamily: 'sans-serif', textAlign: 'center' }}>
        Embed not found.
      </div>
    );
  }
  if (!data) return null;

  return (
    <div ref={containerRef} className={data.page_css_class || 'cms-page'}>
      <BlockRenderer blocks={data.blocks} />
    </div>
  );
};
