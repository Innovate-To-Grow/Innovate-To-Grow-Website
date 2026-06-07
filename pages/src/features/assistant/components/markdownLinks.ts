import {safeHref} from '@/lib/safeHref';

/**
 * True when `href` survives the shared {@link safeHref} scheme allowlist
 * unchanged (http/https/mailto/tel + relative paths). Anything else (e.g.
 * `javascript:`) is rejected and the link text is shown as inert plain text.
 *
 * Delegates to the canonical site-wide helper so assistant links accept
 * exactly the same URLs as CMS/news links do.
 */
export function isSafeHref(href: string | undefined): href is string {
  return typeof href === 'string' && href.length > 0 && safeHref(href) === href;
}
