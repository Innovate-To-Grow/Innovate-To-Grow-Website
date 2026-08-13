import {type User} from '@/features/auth/api/types';
import {formatE164ForDisplay} from '@/features/auth/components/sections/internal/phoneInput';
import {Icon} from '@/components/Icon/Icon';

interface MemberMenuProps {
  user: User | null;
  isAuthenticated: boolean;
  isOpen: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onToggle: () => void;
  onAccountClick: () => void;
  onLoginClick: () => void;
  onLogoutClick: () => void;
}

export const MemberMenu = ({
  user,
  isAuthenticated,
  isOpen,
  onMouseEnter,
  onMouseLeave,
  onToggle,
  onAccountClick,
  onLoginClick,
  onLogoutClick,
}: MemberMenuProps) => (
  <div
    className={`site-header-member${isAuthenticated ? ' is-authenticated' : ''}${isOpen ? ' is-open' : ''}`}
    onMouseEnter={onMouseEnter}
    onMouseLeave={onMouseLeave}
  >
    {isAuthenticated ? (
      <>
        <button
          type="button"
          className="member-button authenticated"
          aria-expanded={isOpen}
          onClick={onToggle}
        >
          {user?.profile_image ? (
            <img src={user.profile_image} alt="" className="member-avatar" />
          ) : (
            <Icon name="user-circle" />
          )}
          <span className="member-name">{user?.email || formatE164ForDisplay(user?.phone ?? '') || 'Member'}</span>
          <Icon name="angle-down" className="member-arrow" />
        </button>
        {isOpen && (
          <div className="member-dropdown">
            <button
              type="button"
              className="member-dropdown-item member-dropdown-item-account"
              onClick={onAccountClick}
            >
              <Icon name="cog" />
              <span>Account</span>
            </button>
            <button type="button" className="member-dropdown-item logout" onClick={onLogoutClick}>
              <Icon name="sign-out" />
              <span>Sign Out</span>
            </button>
          </div>
        )}
      </>
    ) : (
      <button type="button" className="member-button" onClick={onLoginClick}>
        <Icon name="user" />
        <span>Sign In</span>
      </button>
    )}
  </div>
);
