import { Link } from 'react-router';
import { safeHref } from '@/lib/security';

export interface CtaItem {
  label: string;
  /** Link target as the admin block editor stores it. */
  href?: string;
  /** Older/hand-written JSON sometimes uses `url`; accepted as a fallback. */
  url?: string;
  /** Free text in the admin editor: primary, secondary/outline, accent/gold, bright, text/link. */
  style?: string;
}

export interface CtaGroupData {
  items: CtaItem[];
}

type CtaVariant = 'primary' | 'outline' | 'accent' | 'bright' | 'text';

const STYLE_VARIANTS: Record<string, CtaVariant> = {
  primary: 'primary',
  secondary: 'outline',
  outline: 'outline',
  accent: 'accent',
  gold: 'accent',
  bright: 'bright',
  text: 'text',
  link: 'text',
};

/**
 * Map the editor's free-text style to a design-system button. Editors may type
 * the bare name ("primary") or a class ("btn-primary", "itg-btn-primary").
 * Without a recognised style the first button is primary and the rest are
 * outlined, so a row reads as one main action plus secondary ones.
 */
function ctaVariant(style: unknown, index: number): CtaVariant {
  const key = typeof style === 'string' ? style.trim().toLowerCase().replace(/^(itg-)?btn-/, '') : '';
  if (Object.hasOwn(STYLE_VARIANTS, key)) return STYLE_VARIANTS[key];
  return index === 0 ? 'primary' : 'outline';
}

function isExternalHttpUrl(href: string): boolean {
  try {
    const url = new URL(href);
    return (url.protocol === 'http:' || url.protocol === 'https:') && url.origin !== window.location.origin;
  } catch {
    return false;
  }
}

function CtaLink({ href, className, label }: { href: string; className: string; label: string }) {
  if (href.startsWith('/')) {
    return (
      <Link to={href} className={className}>
        {label}
      </Link>
    );
  }
  if (isExternalHttpUrl(href)) {
    return (
      <a href={href} className={className} target="_blank" rel="noopener noreferrer">
        {label}
        <span className="sr-only"> (opens in a new tab)</span>
      </a>
    );
  }
  return (
    <a href={href} className={className}>
      {label}
    </a>
  );
}

export const CtaGroupBlock = ({ data }: { data: CtaGroupData }) => {
  const items = (Array.isArray(data.items) ? data.items : []).filter(
    (item): item is CtaItem => Boolean(item) && typeof item.label === 'string' && item.label.trim() !== '',
  );
  if (items.length === 0) return null;

  return (
    <section className="cms-cta-group">
      <ul className="cms-cta-group-list">
        {items.map((item, i) => {
          // safeHref only lets site-relative paths, #fragments and http(s)/mailto/tel through.
          const href = safeHref(item.href || item.url);
          return (
            <li key={`${href}-${i}`} className="cms-cta-group-item">
              <CtaLink
                href={href}
                className={`itg-btn itg-btn-${ctaVariant(item.style, i)} cms-cta-group-button`}
                label={item.label.trim()}
              />
            </li>
          );
        })}
      </ul>
    </section>
  );
};
