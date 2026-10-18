import {useCallback, useMemo, useRef, useState, type MouseEvent} from 'react';
import {ResponsiveBrandImage} from '@/components/ResponsiveBrandImage';
import {useCurrentPathname} from '@/features/layout/hooks/useCurrentPathname';
import {resolveSection} from '@/features/layout/sections';
import {MemberMenu} from './parts/MemberMenu';
import {MenuTree} from './parts/MenuTree';
import {MobileMenuPanel} from './parts/MobileMenuPanel';
import {MENU_BAR_SKELETON_WIDTHS_PX, UNIVERSITY_LINKS, formatMenuDate} from './parts/shared';
import {useHeaderBandHidden, useHeaderMetrics} from './useHeaderScroll';
import {useMainMenuState} from './useMainMenuState';

interface MainMenuProps {
  navigate?: (to: string) => void;
}

/** Same breakpoint as the layout-menu sheet: at or below it the phone header is shown. */
const PHONE_MAX_WIDTH = 992;

/** Move focus to the page's main landmark without touching the URL (the router owns it). */
const skipToMain = (event: MouseEvent<HTMLAnchorElement>) => {
  const main = document.getElementById('main');
  if (!main) return;
  event.preventDefault();
  if (!main.hasAttribute('tabindex')) main.setAttribute('tabindex', '-1');
  main.focus();
};

export const MainMenu = ({navigate = (to) => window.location.assign(to)}: MainMenuProps) => {
  const {
    hasMemberIdentity,
    isMemberDropdownOpen,
    isMobileOpen,
    logout,
    menuItems,
    navIntroFade,
    openItemIndex,
    setIsMemberDropdownOpen,
    setIsMobileOpen,
    setNavIntroFade,
    setOpenItemIndex,
    state,
    user,
  } = useMainMenuState();

  const headerRef = useRef<HTMLElement>(null);
  const mobileMenuTriggerRef = useRef<HTMLButtonElement>(null);
  const pathname = useCurrentPathname();
  const current = useMemo(() => resolveSection(menuItems, pathname), [menuItems, pathname]);
  const isBandHidden = useHeaderBandHidden(headerRef);
  useHeaderMetrics(headerRef);
  const [today] = useState(() => formatMenuDate(new Date()));

  const toggleMobileMenu = useCallback(
    () => setIsMobileOpen((prev) => !prev),
    [setIsMobileOpen],
  );
  const closeMobileMenu = useCallback(
    () => setIsMobileOpen(false),
    [setIsMobileOpen],
  );

  const handleDesktopToggle = (index: number, hasChildren: boolean) => {
    if (!hasChildren || window.innerWidth <= PHONE_MAX_WIDTH) return;
    setOpenItemIndex((prev) => (prev === index ? null : index));
  };

  const handleDesktopOpen = (index: number, hasChildren: boolean) => {
    if (window.innerWidth > PHONE_MAX_WIDTH && hasChildren) {
      setOpenItemIndex(index);
    }
  };

  const handleDesktopClose = () => {
    if (window.innerWidth > PHONE_MAX_WIDTH) {
      setOpenItemIndex(null);
    }
  };

  return (
    <header
      ref={headerRef}
      className={`site-header${isBandHidden ? ' is-band-hidden' : ''}${isMobileOpen ? ' is-mobile-open' : ''}`}
      role="banner"
    >
      <a className="skip-link" href="#main" onClick={skipToMain}>
        Skip to main content
      </a>

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
            onClick={toggleMobileMenu}
          >
            <span className="site-header-mobile-toggle-bar" />
            <span className="site-header-mobile-toggle-bar" />
            <span className="site-header-mobile-toggle-bar" />
          </button>
        </div>
      </div>

      <div className="site-header-band">
        <div className="site-header-container site-header-band-inner">
          <a className="site-header-sitename" href="/">
            <span className="site-header-sitename-title">Innovate To Grow</span>{' '}
            <span className="site-header-sitename-subtitle">School of Engineering</span>
          </a>
        </div>
      </div>

      <div className="site-header-menu">
        <div className="site-header-container site-header-menu-inner">
          <nav
            className={`site-header-nav${navIntroFade ? ' menu-nav-intro-fade' : ''}`}
            aria-label="Main menu"
            aria-busy={state === 'loading'}
            onAnimationEnd={(e) => {
              if (e.animationName === 'menuNavIntroFade' && e.currentTarget === e.target) {
                setNavIntroFade(false);
              }
            }}
          >
            {state === 'loading' && (
              <ul className="menu-bar-list menu-bar-list--skeleton" aria-hidden="true">
                {MENU_BAR_SKELETON_WIDTHS_PX.map((w, i) => (
                  <li key={i} className="menu-bar-item menu-bar-item--skeleton">
                    <span className="menu-bar-skeleton" style={{width: `${w}px`}} />
                  </li>
                ))}
              </ul>
            )}

            {state === 'error' && (
              <ul className="menu-bar-list">
                <li className="menu-bar-item is-error">
                  <span className="menu-bar-link">Menu unavailable</span>
                </li>
              </ul>
            )}

            {state === 'ready' && menuItems.length > 0 ? (
              <MenuTree
                items={menuItems}
                openItemIndex={openItemIndex}
                current={current}
                onDesktopOpen={handleDesktopOpen}
                onDesktopClose={handleDesktopClose}
                onDesktopToggle={handleDesktopToggle}
              />
            ) : null}

            {state === 'ready' && menuItems.length === 0 ? (
              <ul className="menu-bar-list">
                <li className="menu-bar-item is-muted">
                  <span className="menu-bar-link">No menu items</span>
                </li>
              </ul>
            ) : null}
          </nav>

          <div className="site-header-utility">
            <time className="site-header-date" dateTime={today.iso}>
              {today.label}
            </time>
            <MemberMenu
              user={user}
              hasMemberIdentity={hasMemberIdentity}
              isOpen={isMemberDropdownOpen}
              onMouseEnter={() => hasMemberIdentity && setIsMemberDropdownOpen(true)}
              onMouseLeave={() => setIsMemberDropdownOpen(false)}
              onToggle={() => setIsMemberDropdownOpen((prev) => !prev)}
              onClose={() => setIsMemberDropdownOpen(false)}
              onAccountClick={() => {
                setIsMemberDropdownOpen(false);
                navigate('/account');
              }}
              onLoginClick={() => navigate('/login')}
              onLogoutClick={() => {
                setIsMemberDropdownOpen(false);
                logout();
              }}
            />
          </div>
        </div>
      </div>

      <MobileMenuPanel
        menuItems={menuItems}
        state={state}
        isMobileOpen={isMobileOpen}
        hasMemberIdentity={hasMemberIdentity}
        user={user}
        current={current}
        triggerRef={mobileMenuTriggerRef}
        onClose={closeMobileMenu}
        onAccountClick={() => {
          setIsMobileOpen(false);
          navigate('/account');
        }}
        onLoginClick={() => {
          setIsMobileOpen(false);
          navigate('/login');
        }}
        onLogoutClick={() => {
          setIsMobileOpen(false);
          logout();
        }}
      />
    </header>
  );
};
