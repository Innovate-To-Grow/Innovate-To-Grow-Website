import {useCallback, useRef} from 'react';
import {ResponsiveBrandImage} from '@/components/ResponsiveBrandImage';
import {MemberMenu} from './parts/MemberMenu';
import {MenuTree} from './parts/MenuTree';
import {MobileMenuPanel} from './parts/MobileMenuPanel';
import {MENU_BAR_SKELETON_WIDTHS_PX} from './parts/shared';
import {useMainMenuState} from './useMainMenuState';

interface MainMenuProps {
  navigate?: (to: string) => void;
}

export const MainMenu = ({navigate = (to) => window.location.assign(to)}: MainMenuProps) => {
  const {
    currentDate,
    isAuthenticated,
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

  const mobileMenuTriggerRef = useRef<HTMLButtonElement>(null);
  const toggleMobileMenu = useCallback(
    () => setIsMobileOpen((prev) => !prev),
    [setIsMobileOpen],
  );
  const closeMobileMenu = useCallback(
    () => setIsMobileOpen(false),
    [setIsMobileOpen],
  );

  const handleDesktopToggle = (index: number, hasChildren: boolean) => {
    if (!hasChildren || window.innerWidth <= 992) return;
    setOpenItemIndex((prev) => (prev === index ? null : index));
  };

  const handleDesktopOpen = (index: number, hasChildren: boolean) => {
    if (window.innerWidth > 992 && hasChildren) {
      setOpenItemIndex(index);
    }
  };

  const handleDesktopClose = () => {
    if (window.innerWidth > 992) {
      setOpenItemIndex(null);
    }
  };

  return (
    <header className="site-header" role="banner">
      <div className="site-header-top">
        <div className="site-header-container site-header-top-inner">
          <button
            ref={mobileMenuTriggerRef}
            type="button"
            className={`site-header-mobile-toggle ${isMobileOpen ? 'is-active' : ''}`}
            aria-label="Toggle menu"
            aria-controls="mobile-menu"
            aria-expanded={isMobileOpen}
            onClick={toggleMobileMenu}
          >
            <span className="site-header-mobile-toggle-bar" />
            <span className="site-header-mobile-toggle-bar" />
            <span className="site-header-mobile-toggle-bar" />
          </button>

          <a
            className="ucm-wordmark"
            href="https://www.ucmerced.edu"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="UC Merced"
          >
            <ResponsiveBrandImage brand="ucm" sizes="230px" />
          </a>

          <a className="site-header-top-logo" href="/" aria-label="Innovate To Grow">
            <ResponsiveBrandImage
              brand="fullname"
              className="site-header-top-logo-full"
              sizes="(max-width: 992px) 70vw, 480px"
            />
          </a>

          <div className="site-header-top-links" aria-label="Quick links">
            <a href="https://directory.ucmerced.edu/" target="_blank" rel="noopener noreferrer">
              Directory
            </a>
            <a href="https://admissions.ucmerced.edu/first-year/apply?button" target="_blank" rel="noopener noreferrer">
              Apply
            </a>
            <a href="https://giving.ucmerced.edu/" target="_blank" rel="noopener noreferrer">
              Give
            </a>
          </div>
        </div>
      </div>

      <div className="site-header-bottom">
        <div className="site-header-container site-header-bottom-inner">
          <div className="site-header-bottom-left">
            <a className="site-header-badge" href="/" aria-label="Home">
              <ResponsiveBrandImage brand="i2g" sizes="96px" />
            </a>

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
                      <span className="menu-bar-skeleton" style={{ width: `${w}px` }} />
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
          </div>

          <div className="site-header-date" aria-label="Current date">
            {currentDate}
          </div>

          <MemberMenu
            user={user}
            isAuthenticated={isAuthenticated}
            isOpen={isMemberDropdownOpen}
            onMouseEnter={() => isAuthenticated && setIsMemberDropdownOpen(true)}
            onMouseLeave={() => setIsMemberDropdownOpen(false)}
            onToggle={() => setIsMemberDropdownOpen((prev) => !prev)}
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

      <MobileMenuPanel
        menuItems={menuItems}
        state={state}
        isMobileOpen={isMobileOpen}
        isAuthenticated={isAuthenticated}
        user={user}
        openItemIndex={openItemIndex}
        triggerRef={mobileMenuTriggerRef}
        onClose={closeMobileMenu}
        onDesktopOpen={handleDesktopOpen}
        onDesktopClose={handleDesktopClose}
        onDesktopToggle={handleDesktopToggle}
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
