import {
  type FooterCTAButton,
  type FooterLink,
  type FooterSocialLink,
} from '../../../services/api';
import { useFooter } from '../LayoutProvider/context';
import './Footer.css';

const buttonColor = (style?: FooterCTAButton['style']) => (style === 'gold' ? 'gold' : 'blue');

const FooterLinkItem = ({ link }: { link: FooterLink }) => (
  <li>
    <a href={link.href} target={link.target || undefined} rel={link.rel || undefined}>
      {link.label}
    </a>
  </li>
);

const SocialIcon = ({ link }: { link: FooterSocialLink }) => (
  <li className="fa-li">
    <a
      href={link.href}
      target={link.target || undefined}
      rel={link.rel || undefined}
      aria-label={link.aria_label || undefined}
    >
      <i className={link.icon_class} />
    </a>
  </li>
);

export const Footer = () => {
  const { footer: footerContent, state, error } = useFooter();

  if (state === 'loading') {
    return null;
  }

  if (state === 'error' || error) {
    return (
      <div className="container">
        <div className="footer-error" role="status">{error || 'Footer is currently unavailable.'}</div>
      </div>
    );
  }

  if (!footerContent) {
    return null;
  }

  const { content } = footerContent;
  const columns = content.columns ?? [];
  const socialLinks = content.social_links ?? [];
  const footerLinks = content.footer_links ?? [];

  const hasFooterLinks = footerLinks.length > 0;
  const hasCopyright = Boolean(content.copyright);
  const shouldShowFooterBottom = hasFooterLinks || hasCopyright;

  return (
    <>
      {content.cta_buttons?.length ? (
        <div className="sb-row home-cta-row">
          {content.cta_buttons.map((cta, index) => {
            const color = buttonColor(cta.style);
            return (
              <div key={`${cta.label}-${index}`} className={`sb-col hb__buttons-${color}`}>
                <a className={`btn--invert-${color} hb__play`} href={cta.href}>
                  {cta.label}
                </a>
              </div>
            );
          })}

          {content.contact_html ? (
            <div className="i2gHome" dangerouslySetInnerHTML={{ __html: content.contact_html }} />
          ) : null}
        </div>
      ) : null}

      <footer id="footer" className="site-footer" role="contentinfo">
        <div className="footer-main">
          <div className="footer-container">
            <div className="footer-columns">
              {columns.map((column, index) => {
                const isAddressColumn = index === columns.length - 1;
                return (
                  <div
                    key={`${column.title || 'column'}-${index}`}
                    className={`footer-column${isAddressColumn ? ' footer-column--address' : ''}`}
                  >
                    {column.title ? <h2>{column.title}</h2> : null}

                    {column.links?.length ? (
                      <ul>
                        {column.links.map((link, linkIndex) => (
                          <FooterLinkItem key={`${link.label}-${linkIndex}`} link={link} />
                        ))}
                      </ul>
                    ) : null}

                    {column.body_html ? (
                      <div className="footer-column__body" dangerouslySetInnerHTML={{ __html: column.body_html }} />
                    ) : null}

                    {isAddressColumn && socialLinks.length ? (
                      <div className="socialIcons">
                        <ul className="fa-ul inline">
                          {socialLinks.map((link, linkIndex) => (
                            <SocialIcon key={`${link.href}-${linkIndex}`} link={link} />
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {shouldShowFooterBottom ? (
          <div className="footer-bottom">
            <div className="footer-container">
              <ul className="footer-meta">
                {content.copyright ? <li>{content.copyright}</li> : null}
                {footerLinks.map((link, index) => (
                  <FooterLinkItem key={`${link.label}-${index}`} link={link} />
                ))}
              </ul>
            </div>
          </div>
        ) : null}
      </footer>
    </>
  );
};
