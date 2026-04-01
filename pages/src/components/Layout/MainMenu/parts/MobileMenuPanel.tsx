import {type MenuItem} from '../../../../features/layout/api';
import {type User} from '../../../../shared/auth/types';
import {type LayoutLoadState} from '../../LayoutProvider/context';
import {MenuTree} from './MenuTree';
import {MENU_BAR_SKELETON_WIDTHS_PX} from './shared';

interface MobileMenuPanelProps {
  menuItems: MenuItem[];
  state: LayoutLoadState;
  isMobileOpen: boolean;
  isAuthenticated: boolean;
  user: User | null;
  openItemIndex: number | null;
  onClose: () => void;
  onDesktopOpen: (index: number, hasChildren: boolean) => void;
  onDesktopClose: () => void;
  onDesktopToggle: (index: number, hasChildren: boolean) => void;
  onAccountClick: () => void;
  onLoginClick: () => void;
  onLogoutClick: () => void;
}

export const MobileMenuPanel = ({
  menuItems,
  state,
  isMobileOpen,
  isAuthenticated,
  user,
  openItemIndex,
  onClose,
  onDesktopOpen,
  onDesktopClose,
  onDesktopToggle,
  onAccountClick,
  onLoginClick,
  onLogoutClick,
}: MobileMenuPanelProps) => (
  <>
    <div
      className={`header-mobile-overlay ${isMobileOpen ? 'is-open' : ''}`}
      onClick={onClose}
      aria-hidden="true"
    />

    <div
      id="mobile-menu"
      className={`header-mobile-menu ${isMobileOpen ? 'is-open' : ''}`}
      aria-label="Mobile menu"
    >
      <div className="header-mobile-top">
        <a href="/" className="header-mobile-brand">
          <img src="/assets/images/i2glogo.png" alt="I2G" className="header-mobile-logo" width={2038} height={2039} />
          <span>Innovate To Grow</span>
        </a>
        <button type="button" className="header-mobile-close" aria-label="Close menu" onClick={onClose}>
          <i className="fa fa-times" />
        </button>
      </div>

      <nav className="header-mobile-nav" aria-busy={state === 'loading'}>
        {state === 'loading' && (
          <ul className="header-mobile-nav-skeleton" aria-hidden="true">
            {MENU_BAR_SKELETON_WIDTHS_PX.map((w, i) => (
              <li key={i} className="header-mobile-nav-skeleton-row">
                <span className="menu-bar-skeleton" style={{width: `${Math.min(w + 24, 200)}px`}} />
              </li>
            ))}
          </ul>
        )}
        {state === 'ready' && menuItems.length > 0 && (
          <MenuTree
            items={menuItems}
            openItemIndex={openItemIndex}
            onDesktopOpen={onDesktopOpen}
            onDesktopClose={onDesktopClose}
            onDesktopToggle={onDesktopToggle}
          />
        )}
      </nav>

      <div className="header-mobile-member">
        {isAuthenticated ? (
          <>
            <div className="header-mobile-member-info">
              {user?.profile_image ? (
                <img src={user.profile_image} alt="" className="header-mobile-member-avatar" />
              ) : (
                <i className="fa fa-user-circle" />
              )}
              <span>{user?.email || 'Member'}</span>
            </div>
            <div className="header-mobile-member-actions">
              <button type="button" className="header-mobile-action" onClick={onAccountClick}>
                Account
              </button>
              <button type="button" className="header-mobile-action" onClick={onLogoutClick}>
                Sign Out
              </button>
            </div>
          </>
        ) : (
          <button type="button" className="header-mobile-action primary" onClick={onLoginClick}>
            <i className="fa fa-user" />
            Sign In / Sign Up
          </button>
        )}
      </div>

      <div className="header-mobile-actions">
        <a
          href="https://directory.ucmerced.edu/"
          target="_blank"
          rel="noopener noreferrer"
          className="header-mobile-action"
        >
          Directory
        </a>
        <a
          href="https://admissions.ucmerced.edu/first-year/apply?button"
          target="_blank"
          rel="noopener noreferrer"
          className="header-mobile-action primary"
        >
          Apply Now
        </a>
        <a href="http://giving.ucmerced.edu/" target="_blank" rel="noopener noreferrer" className="header-mobile-action">
          Give
        </a>
      </div>

      <div className="header-mobile-footer">
        <a href="https://www.ucmerced.edu" target="_blank" rel="noopener noreferrer">
          <img src="/assets/images/ucmlogo.png" alt="UC Merced" width={230} height={57} />
        </a>
      </div>
    </div>
  </>
);
