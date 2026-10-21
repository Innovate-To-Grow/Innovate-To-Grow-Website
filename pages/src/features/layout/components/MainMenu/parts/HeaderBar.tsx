import type {RefObject} from 'react';
import {ResponsiveBrandImage} from '@/components/ResponsiveBrandImage';
import {PHONE_MAX_WIDTH, UNIVERSITY_LINKS} from './shared';

interface HeaderBarProps {
  isMobileOpen: boolean;
  mobileMenuTriggerRef: RefObject<HTMLButtonElement | null>;
  onToggleMobileMenu: () => void;
}

/** The top bar: UC Merced wordmark, the I2G logo, university links and the phone menu toggle. */
export const HeaderBar = ({isMobileOpen, mobileMenuTriggerRef, onToggleMobileMenu}: HeaderBarProps) => (
  <div className="site-header-bar">
    <div className="site-header-container site-header-bar-inner">
      <a
        className="ucm-wordmark"
        href="https://www.ucmerced.edu"
        target="_blank"
        rel="noopener noreferrer"
        aria-label="UC Merced"
      >
        <ResponsiveBrandImage brand="ucm" alt="" sizes="(max-width: 992px) 114px, 138px" />
      </a>

      <a className="site-header-logo" href="/" aria-label="Innovate To Grow home">
        <ResponsiveBrandImage
          brand="fullname"
          alt=""
          className="site-header-logo-image"
          sizes="156px"
          artDirection={{media: `(max-width: ${PHONE_MAX_WIDTH}px)`, brand: 'i2g', sizes: '50px'}}
        />
      </a>

      <nav className="site-header-links" aria-label="UC Merced">
        {UNIVERSITY_LINKS.map((link) => (
          <a key={link.label} href={link.href} target="_blank" rel="noopener noreferrer">
            {link.label}
          </a>
        ))}
      </nav>

      <button
        ref={mobileMenuTriggerRef}
        type="button"
        className={`site-header-mobile-toggle${isMobileOpen ? ' is-active' : ''}`}
        aria-label="Toggle menu"
        aria-controls="mobile-menu"
        aria-expanded={isMobileOpen}
        onClick={onToggleMobileMenu}
      >
        <span className="site-header-mobile-toggle-bar" />
        <span className="site-header-mobile-toggle-bar" />
        <span className="site-header-mobile-toggle-bar" />
      </button>
    </div>
  </div>
);
