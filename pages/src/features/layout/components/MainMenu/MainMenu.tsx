import './MainMenu.css';
import {useCallback, useMemo, useRef, useState, type MouseEvent} from 'react';
import {useCurrentPathname} from '@/features/layout/hooks/useCurrentPathname';
import {resolveSection} from '@/features/layout/sections';
import {DesktopMenuNav} from './parts/DesktopMenuNav';
import {HeaderBar} from './parts/HeaderBar';
import {MemberMenu} from './parts/MemberMenu';
import {MobileMenuPanel} from './parts/MobileMenuPanel';
import {formatMenuDate} from './parts/shared';
import {useHeaderBandHidden, useHeaderMetrics} from './useHeaderScroll';
import {useMainMenuState} from './useMainMenuState';

interface MainMenuProps {
  navigate?: (to: string) => void;
}

/** Move focus to the page's main landmark without touching the URL (the router owns it). */
const skipToMain = (event: MouseEvent<HTMLAnchorElement>) => {
  const main = document.getElementById('main');
  if (!main) return;
  event.preventDefault();
  if (!main.hasAttribute('tabindex')) main.setAttribute('tabindex', '-1');
  main.focus();
};

const SiteNameBand = () => (
  <div className="site-header-band">
    <div className="site-header-container site-header-band-inner">
      <a className="site-header-sitename" href="/">
        <span className="site-header-sitename-title">Innovate To Grow</span>{' '}
        <span className="site-header-sitename-subtitle">School of Engineering</span>
      </a>
    </div>
  </div>
);

interface MemberMenuHandlerOptions {
  hasMemberIdentity: boolean;
  isMemberDropdownOpen: boolean;
  setIsMemberDropdownOpen: (open: boolean | ((prev: boolean) => boolean)) => void;
  navigate: (to: string) => void;
  logout: () => void;
}

/** The account menu opens on hover or click, and closes when the pointer leaves, on close, or after an action. */
const useMemberMenuHandlers = ({
  hasMemberIdentity,
  isMemberDropdownOpen,
  setIsMemberDropdownOpen,
  navigate,
  logout,
}: MemberMenuHandlerOptions) => {
  // Set while the account menu is open only because the pointer is over it. The click that
  // follows that hover then keeps the menu open instead of toggling it shut again.
  const memberMenuHoverOpenRef = useRef(false);
  const close = () => {
    memberMenuHoverOpenRef.current = false;
    setIsMemberDropdownOpen(false);
  };
  return {
    onMouseEnter: () => {
      if (!hasMemberIdentity || isMemberDropdownOpen) return;
      memberMenuHoverOpenRef.current = true;
      setIsMemberDropdownOpen(true);
    },
    onMouseLeave: close,
    onToggle: () => {
      const openedByHover = memberMenuHoverOpenRef.current;
      memberMenuHoverOpenRef.current = false;
      setIsMemberDropdownOpen((prev) => openedByHover || !prev);
    },
    onClose: close,
    onAccountClick: () => {
      close();
      navigate('/account');
    },
    onLoginClick: () => navigate('/login'),
    onLogoutClick: () => {
      close();
      logout();
    },
  };
};

export const MainMenu = ({navigate = (to) => window.location.assign(to)}: MainMenuProps) => {
  const menu = useMainMenuState();
  const {
    hasMemberIdentity,
    isMemberDropdownOpen,
    isMobileOpen,
    logout,
    menuItems,
    setIsMemberDropdownOpen,
    setIsMobileOpen,
    state,
    user,
  } = menu;

  const headerRef = useRef<HTMLElement>(null);
  const mobileMenuTriggerRef = useRef<HTMLButtonElement>(null);
  const pathname = useCurrentPathname();
  const current = useMemo(() => resolveSection(menuItems, pathname), [menuItems, pathname]);
  const isBandHidden = useHeaderBandHidden(headerRef);
  useHeaderMetrics(headerRef);
  const [today] = useState(() => formatMenuDate(new Date()));
  const memberMenuHandlers = useMemberMenuHandlers({
    hasMemberIdentity,
    isMemberDropdownOpen,
    setIsMemberDropdownOpen,
    navigate,
    logout,
  });

  const toggleMobileMenu = useCallback(
    () => setIsMobileOpen((prev) => !prev),
    [setIsMobileOpen],
  );
  const closeMobileMenu = useCallback(
    () => setIsMobileOpen(false),
    [setIsMobileOpen],
  );

  return (
    <header
      ref={headerRef}
      className={`site-header${isBandHidden ? ' is-band-hidden' : ''}${isMobileOpen ? ' is-mobile-open' : ''}`}
      role="banner"
    >
      <a className="skip-link" href="#main" onClick={skipToMain}>
        Skip to main content
      </a>

      <HeaderBar
        isMobileOpen={isMobileOpen}
        mobileMenuTriggerRef={mobileMenuTriggerRef}
        onToggleMobileMenu={toggleMobileMenu}
      />

      <SiteNameBand />

      <div className="site-header-menu">
        <div className="site-header-container site-header-menu-inner">
          <DesktopMenuNav menu={menu} current={current} />

          <div className="site-header-utility">
            <time className="site-header-date" dateTime={today.iso}>
              {today.label}
            </time>
            <MemberMenu
              user={user}
              hasMemberIdentity={hasMemberIdentity}
              isOpen={isMemberDropdownOpen}
              {...memberMenuHandlers}
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
