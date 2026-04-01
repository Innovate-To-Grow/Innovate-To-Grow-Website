import {type User} from '../../../../shared/auth/types';

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
            <i className="fa fa-user-circle" />
          )}
          <span className="member-name">{user?.email || 'Member'}</span>
          <i className="fa fa-angle-down member-arrow" />
        </button>
        {isOpen && (
          <div className="member-dropdown">
            <button
              type="button"
              className="member-dropdown-item member-dropdown-item-account"
              onClick={onAccountClick}
            >
              <i className="fa fa-cog" />
              <span>Account</span>
            </button>
            <button type="button" className="member-dropdown-item logout" onClick={onLogoutClick}>
              <i className="fa fa-sign-out" />
              <span>Sign Out</span>
            </button>
          </div>
        )}
      </>
    ) : (
      <button type="button" className="member-button" onClick={onLoginClick}>
        <i className="fa fa-user" />
        <span>Sign In</span>
      </button>
    )}
  </div>
);
