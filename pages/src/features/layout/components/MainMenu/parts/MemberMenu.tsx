import {type FocusEvent, type KeyboardEvent, type MouseEvent} from 'react';
import {type User} from '@/features/auth/api/types';
import {formatE164ForDisplay} from '@/lib/format/phoneInput';
import {Icon} from '@/components/Icon/Icon';
import {memberButtonLabel, memberDisplayName} from './shared';

interface MemberMenuProps {
  user: User | null;
  /** Render the member view. True as soon as a persisted identity exists, so a background
   *  session check never flashes the anonymous header at a signed-in member. */
  hasMemberIdentity: boolean;
  isOpen: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onToggle: () => void;
  /** Close the account menu (Escape, or focus leaving it). Defaults to a no-op. */
  onClose?: () => void;
  onAccountClick: () => void;
  onLoginClick: () => void;
  onLogoutClick: () => void;
}

const isModifiedClick = (event: MouseEvent<HTMLAnchorElement>) =>
  event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;

export const MemberMenu = ({
  user,
  hasMemberIdentity,
  isOpen,
  onMouseEnter,
  onMouseLeave,
  onToggle,
  onClose,
  onAccountClick,
  onLoginClick,
  onLogoutClick,
}: MemberMenuProps) => {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && isOpen) {
      event.preventDefault();
      onClose?.();
      event.currentTarget.querySelector<HTMLButtonElement>('.member-button')?.focus();
    }
  };

  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (isOpen && !event.currentTarget.contains(event.relatedTarget as Node | null)) {
      onClose?.();
    }
  };

  const label = memberButtonLabel(user, formatE164ForDisplay);

  return (
    <div
      className={`site-header-member${hasMemberIdentity ? ' is-authenticated' : ''}${isOpen ? ' is-open' : ''}`}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onKeyDown={handleKeyDown}
      onBlur={handleBlur}
    >
      {hasMemberIdentity ? (
        <>
          <button
            type="button"
            className="member-button authenticated"
            aria-expanded={isOpen}
            aria-controls="member-dropdown"
            title={label}
            onClick={onToggle}
          >
            {user?.profile_image ? <img src={user.profile_image} alt="" className="member-avatar" /> : null}
            <span className="member-label">{label}</span>
            <Icon name="angle-down" className="member-arrow" />
          </button>
          {isOpen && (
            <div className="member-dropdown" id="member-dropdown">
              <p className="member-dropdown-identity">
                <span className="member-dropdown-identity-label">Signed in as</span>
                <span className="member-name">{memberDisplayName(user, formatE164ForDisplay)}</span>
              </p>
              <button
                type="button"
                className="member-dropdown-item member-dropdown-item-account"
                onClick={onAccountClick}
              >
                Account
              </button>
              <button type="button" className="member-dropdown-item logout" onClick={onLogoutClick}>
                Sign Out
              </button>
            </div>
          )}
        </>
      ) : (
        <a
          href="/login"
          className="member-signin"
          onClick={(event) => {
            if (isModifiedClick(event)) return;
            event.preventDefault();
            onLoginClick();
          }}
        >
          Sign in
        </a>
      )}
    </div>
  );
};
