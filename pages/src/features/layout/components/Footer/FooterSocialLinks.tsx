import {type FooterSocialLink} from '@/features/layout/api';
import {safeHref} from '@/lib/security';
import {Icon} from '@/components/Icon/Icon';

/** "fa fa-linkedin" -> "linkedin" */
const iconName = (iconClass: string) =>
  iconClass
    .split(/\s+/)
    .find((part) => part.startsWith('fa-') && part !== 'fa-fw')
    ?.slice(3)
    .replace(/-(square|official|f)$/, '') ?? '';

/** "fa fa-linkedin" -> "Linkedin"; used when the CMS row has no aria label. */
const socialNameFromIcon = (iconClass: string) => {
  const name = iconName(iconClass);
  return name ? name.charAt(0).toUpperCase() + name.slice(1) : '';
};

const socialLabel = (link: FooterSocialLink) =>
  link.aria_label?.trim() || socialNameFromIcon(link.icon_class ?? '') || link.href;

/** The reference shows Twitter as the X mark. */
const XMark = () => (
  <svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor" aria-hidden="true" focusable="false">
    <path d="M18.9 1.15h3.68l-8.04 9.19L24 22.85h-7.41l-5.8-7.58-6.64 7.58H.47l8.6-9.83L0 1.15h7.6l5.24 6.93zM17.61 20.64h2.04L6.49 3.24H4.3z" />
  </svg>
);

const SocialGlyph = ({ iconClass }: { iconClass: string }) => {
  const name = iconName(iconClass);
  if (!name) return null;
  if (name === 'twitter' || name === 'x-twitter') return <XMark />;
  return <Icon name={iconClass} className="footer-social-icon" />;
};

/** Round navy icons (white glyph); the name stays readable to screen readers. */
export const SocialLinks = ({ links }: { links: FooterSocialLink[] }) => (
  <ul className="footer-social">
    {links.map((link, index) => {
      const hasGlyph = Boolean(iconName(link.icon_class ?? ''));
      return (
        <li key={`${link.href}-${index}`}>
          <a
            className={hasGlyph ? 'footer-social-link' : 'footer-social-link is-text'}
            href={safeHref(link.href)}
            target={link.target || undefined}
            rel={link.rel || undefined}
          >
            <SocialGlyph iconClass={link.icon_class ?? ''} />
            <span className={hasGlyph ? 'sr-only' : undefined}>{socialLabel(link)}</span>
          </a>
        </li>
      );
    })}
  </ul>
);
