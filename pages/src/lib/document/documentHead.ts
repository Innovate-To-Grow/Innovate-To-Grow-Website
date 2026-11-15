/**
 * The page-level tags in <head> that the SPA keeps in step with the route: meta description (and its
 * og: twin), robots noindex, canonical URL and og:title / og:url. pages/index.html carries the site-wide
 * defaults, which is all a link unfurler sees (they do not run scripts); search engines that render the
 * page see the per-route values written here.
 *
 * Several components can ask for tags at once (the route's defaults, then the page itself), so each
 * request is a claim that is withdrawn on cleanup: the newest page claim wins over route claims, which
 * win over the index.html default, and any claim can mark the page noindex.
 */

export type HeadClaimLevel = 'route' | 'page';

export interface HeadClaim {
  description?: string | null;
  noindex?: boolean;
}

interface RegisteredClaim extends HeadClaim {
  level: HeadClaimLevel;
}

const claims: RegisteredClaim[] = [];
/** The index.html description, read again whenever no claim is active (so it is never a claim's). */
let defaultDescription = '';

function upsertMeta(attribute: 'name' | 'property', key: string, content: string | null): void {
  let meta = document.head.querySelector<HTMLMetaElement>(`meta[${attribute}="${key}"]`);
  if (!content) {
    meta?.remove();
    return;
  }
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute(attribute, key);
    document.head.appendChild(meta);
  }
  if (meta.content !== content) meta.content = content;
}

function newestDescription(level: HeadClaimLevel): string | undefined {
  for (let index = claims.length - 1; index >= 0; index -= 1) {
    const claim = claims[index];
    const description = claim.description?.trim();
    if (claim.level === level && description) return description;
  }
  return undefined;
}

function applyClaims(): void {
  const description = newestDescription('page') ?? newestDescription('route') ?? defaultDescription;
  upsertMeta('name', 'description', description);
  upsertMeta('property', 'og:description', description);
  upsertMeta('name', 'robots', claims.some((claim) => claim.noindex) ? 'noindex' : null);
}

/** Registers a claim on the head tags and applies it; the returned function withdraws it. */
export function claimDocumentHead(claim: HeadClaim, level: HeadClaimLevel): () => void {
  if (claims.length === 0) {
    defaultDescription = document.head.querySelector<HTMLMetaElement>('meta[name="description"]')?.content ?? '';
  }
  const registered: RegisteredClaim = {...claim, level};
  claims.push(registered);
  applyClaims();
  return () => {
    claims.splice(claims.indexOf(registered), 1);
    applyClaims();
  };
}

/** og:title follows the tab title, without the site name (og:site_name carries that). */
export function setOpenGraphTitle(title: string): void {
  upsertMeta('property', 'og:title', title);
}

/** The page's canonical URL (and og:url): its address without the query string or fragment. */
export function setCanonicalUrl(url: string): void {
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'canonical';
    document.head.appendChild(link);
  }
  if (link.href !== url) link.href = url;
  upsertMeta('property', 'og:url', url);
}
