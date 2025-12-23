import { useEffect, useState } from 'react';
import {
  fetchFooterContent,
  type FooterContentResponse,
  type FooterCTAButton,
  type FooterLink,
  type FooterSocialLink,
} from '../../services/api';

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
  const [footerContent, setFooterContent] = useState<FooterContentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadFooter = async () => {
      try {
        const data = await fetchFooterContent();
        setFooterContent(data);
      } catch (err) {
        console.error('Unable to load footer content', err);
        setError('Footer is currently unavailable.');
      }
    };

    loadFooter();
  }, []);

  if (error) {
    return (
      <div className="container">
        <div className="footer-error" role="status">{error}</div>
      </div>
    );
  }

  if (!footerContent) {
    return null;
  }

  const { content } = footerContent;

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

      <div id="footer" className="clearfix site-footer" role="contentinfo">
        <div className="container">
          <div id="footer-content" className="row-fluid footer-content" />
        </div>

        <div className="final-foot">
          <div className="container">
            <div className="footer-links">
              {content.columns?.map((column, index) => (
                <div
                  key={`${column.title || 'column'}-${index}`}
                  className={`fColumn${index === content.columns.length - 1 ? ' fAddress' : ''}`}
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
                    <div dangerouslySetInnerHTML={{ __html: column.body_html }} />
                  ) : null}

                  {index === content.columns.length - 1 && content.social_links?.length ? (
                    <div className="socialIcons">
                      <ul className="fa-ul inline">
                        {content.social_links.map((link, linkIndex) => (
                          <SocialIcon key={`${link.href}-${linkIndex}`} link={link} />
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </div>

        {content.footer_links?.length ? (
          <div className="copyright">
            <ul>
              {content.copyright ? <li>{content.copyright}</li> : null}
              {content.footer_links.map((link, index) => (
                <FooterLinkItem key={`${link.label}-${index}`} link={link} />
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </>
  );
};
