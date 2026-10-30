import './MainMenu.css';
import {useCallback, useMemo, useRef, useState, type MouseEvent} from 'react';
import {ResponsiveBrandImage} from '@/components/ResponsiveBrandImage';
import {useCurrentPathname} from '@/features/layout/hooks/useCurrentPathname';
import {resolveSection} from '@/features/layout/sections';
import {DesktopMenuNav} from './parts/DesktopMenuNav';
import {HeaderBar} from './parts/HeaderBar';
import {MemberMenu} from './parts/MemberMenu';
import {MobileMenuPanel} from './parts/MobileMenuPanel';
import {formatMenuDate} from './parts/shared';
import {useHeaderDateHidden} from './useHeaderDateFit';
import {useHeaderCondensed, useHeaderMetrics} from './useHeaderScroll';
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

/** The round i2G logo at the front of the menu row: shown only while the condensed row is pinned (menu-row.css). */
const MenuRowLogo = () => (
  <a className="site-header-menu-logo" href="/" aria-label="Innovate To Grow home">
    <ResponsiveBrandImage brand="i2g" alt="" sizes="32px" />
  </a>
);

const headerClassName = (flags: Record<string, boolean>) =>
  ['site-header', ...Object.entries(flags).filter(([, on]) => on).map(([name]) => name)].join(' ');

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
  const {isCondensed, hasMotion} = useHeaderCondensed(headerRef);
  const isDateHidden = useHeaderDateHidden(headerRef);
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
      className={headerClassName({
        'is-condensed': isCondensed,
        'has-motion': hasMotion,
        'is-date-hidden': isDateHidden,
        'is-mobile-open': isMobileOpen,
      })}
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

      <div className="site-header-menu">
        <div className="site-header-container site-header-menu-inner">
          <MenuRowLogo />
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
