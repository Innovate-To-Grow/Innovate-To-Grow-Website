import './Footer.css';
import {
  type FooterColumn,
  type FooterContentData,
  type FooterCTAButton,
  type FooterLink,
  type FooterSocialLink,
} from '@/features/layout/api';
import { safeHref } from '@/lib/security';
import {SafeHtml} from '@/components/SafeHtml/SafeHtml';
import {Icon} from '@/components/Icon/Icon';
import { useFooter } from '../LayoutProvider/context';

const buttonColor = (style?: FooterCTAButton['style']) => (style === 'gold' ? 'gold' : 'blue');

const FooterLinkItem = ({ link }: { link: FooterLink }) => (
  <li>
    <a href={safeHref(link.href)} target={link.target || undefined} rel={link.rel || undefined}>
      {link.label}
    </a>
  </li>
);

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
const SocialLinks = ({ links }: { links: FooterSocialLink[] }) => (
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

interface FooterColumnBlockProps {
  column: FooterColumn;
  socialLinks: FooterSocialLink[];
  isAddressColumn: boolean;
}

const FooterColumnBlock = ({ column, socialLinks, isAddressColumn }: FooterColumnBlockProps) => {
  const links = column.links ?? [];
  return (
    <div className={`footer-column${isAddressColumn ? ' footer-column--address' : ''}`}>
      {/* The reference's contact block has no visible heading; keep it for the outline. */}
      {column.title ? (
        <h2 className={isAddressColumn ? 'footer-column-title sr-only' : 'footer-column-title'}>{column.title}</h2>
      ) : null}
      {links.length ? (
        <ul className="footer-links">
          {links.map((link, linkIndex) => (
            <FooterLinkItem key={`${link.label}-${linkIndex}`} link={link} />
          ))}
        </ul>
      ) : null}
      {column.body_html ? <SafeHtml className="footer-column__body" html={column.body_html} /> : null}
      {isAddressColumn && socialLinks.length ? <SocialLinks links={socialLinks} /> : null}
    </div>
  );
};

type Content = FooterContentData;

/** The white band above the footer: outlined CTA buttons and the contact line. */
const FooterCtaArea = ({content}: {content: Content}) => {
  const ctaButtons = content.cta_buttons ?? [];
  if (!ctaButtons.length && !content.contact_html) return null;
  return (
    <div className="site-footer-cta">
      <div className="footer-container">
        {ctaButtons.length ? (
          <ul className="site-footer-cta-list">
            {ctaButtons.map((cta, index) => {
              const color = buttonColor(cta.style);
              return (
                <li key={`${cta.label}-${index}`} className={`site-footer-cta-item is-${color}`}>
                  <a className={`site-footer-cta-link is-${color}`} href={safeHref(cta.href)}>
                    {cta.label}
                  </a>
                </li>
              );
            })}
          </ul>
        ) : null}

        {content.contact_html ? <SafeHtml className="site-footer-cta-contact" html={content.contact_html} /> : null}
      </div>
    </div>
  );
};

/** The grey band: link columns, the last one with the address and social icons. */
const FooterColumns = ({content}: {content: Content}) => {
  const columns = content.columns ?? [];
  const socialLinks = content.social_links ?? [];
  if (!columns.length) return null;
  return (
    <div className="footer-main">
      <div className="footer-main-inner">
        <div className="footer-columns">
          {columns.map((column, index) => (
            <FooterColumnBlock
              key={`${column.title || 'column'}-${index}`}
              column={column}
              socialLinks={socialLinks}
              isAddressColumn={index === columns.length - 1}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

/** The navy bar: copyright and footer links. */
const FooterBottom = ({content}: {content: Content}) => {
  const footerLinks = content.footer_links ?? [];
  if (!footerLinks.length && !content.copyright) return null;
  return (
    <div className="footer-bottom">
      <div className="footer-container">
        <ul className="footer-meta">
          {content.copyright ? <li className="footer-meta-copyright">{content.copyright}</li> : null}
          {footerLinks.map((link, index) => (
            <FooterLinkItem key={`${link.label}-${index}`} link={link} />
          ))}
        </ul>
      </div>
    </div>
  );
};

/**
 * Site footer, as on the reference site (2026): a centred row of outlined CTA
 * buttons and the contact line on white, the grey band with centred link
 * columns and the address + social icons, then the navy copyright bar.
 */
export const Footer = () => {
  const { footer: footerContent, state, error } = useFooter();

  if (state === 'loading') {
    return null;
  }

  if (state === 'error' || error) {
    return (
      <div className="footer-container">
        <div className="footer-error" role="status">{error || 'Footer is currently unavailable.'}</div>
      </div>
    );
  }

  if (!footerContent) {
    return null;
  }

  const { content } = footerContent;

  return (
    <footer id="footer" className="site-footer" role="contentinfo">
      <FooterCtaArea content={content} />

      <FooterColumns content={content} />

      <FooterBottom content={content} />
    </footer>
  );
};
