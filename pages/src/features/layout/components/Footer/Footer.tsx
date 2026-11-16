import './Footer.css';
import {
  type FooterColumn,
  type FooterContentData,
  type FooterCTAButton,
  type FooterLink,
  type FooterSocialLink,
} from '@/features/layout/api';
import {safeHref} from '@/lib/security';
import {SafeHtml} from '@/components/SafeHtml/SafeHtml';
import {useFooter} from '../LayoutProvider/context';
import {SocialLinks} from './FooterSocialLinks';

const buttonColor = (style?: FooterCTAButton['style']) => (style === 'gold' ? 'gold' : 'blue');

const FooterLinkItem = ({ link }: { link: FooterLink }) => (
  <li>
    <a href={safeHref(link.href)} target={link.target || undefined} rel={link.rel || undefined}>
      {link.label}
    </a>
  </li>
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
