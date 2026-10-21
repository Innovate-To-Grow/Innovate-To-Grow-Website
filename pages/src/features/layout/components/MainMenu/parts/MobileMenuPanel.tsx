import {useEffect, useRef, type RefObject} from 'react';
import {type MenuItem} from '@/features/layout/api';
import {type User} from '@/features/auth/api/types';
import {formatE164ForDisplay} from '@/lib/format/phoneInput';
import {ResponsiveBrandImage} from '@/components/ResponsiveBrandImage';
import {Icon} from '@/components/Icon/Icon';
import {type SectionMatch} from '@/features/layout/sections';
import {type LayoutLoadState} from '../../LayoutProvider/context';
import {MobileMenuTree} from './MobileMenuTree';
import {MENU_BAR_SKELETON_WIDTHS_PX, UNIVERSITY_LINKS, memberDisplayName} from './shared';

interface MobileMenuPanelProps {
  menuItems: MenuItem[];
  state: LayoutLoadState;
  isMobileOpen: boolean;
  hasMemberIdentity: boolean;
  user: User | null;
  /** Current section + page, used to expand the current section and mark aria-current. */
  current?: Pick<SectionMatch, 'menuIndex' | 'currentPath' | 'isExact'> | null;
  triggerRef: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onAccountClick: () => void;
  onLoginClick: () => void;
  onLogoutClick: () => void;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const isVisible = (element: HTMLElement) => !element.closest('[hidden]');

/**
 * While ``isOpen``: focus the first control, keep Tab inside the panel, close on Escape; on close,
 * return focus to the menu button.
 */
const useDialogFocusTrap = (
  panelRef: RefObject<HTMLDivElement | null>,
  isOpen: boolean,
  onClose: () => void,
  triggerRef: RefObject<HTMLButtonElement | null>,
) => {
  useEffect(() => {
    if (!isOpen) return;
    const panel = panelRef.current;
    if (!panel) return;
    const trigger = triggerRef.current;

    const animationFrame = window.requestAnimationFrame(() => {
      panel.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;

      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(isVisible);
      if (!focusable.length) {
        event.preventDefault();
        panel.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !panel.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.cancelAnimationFrame(animationFrame);
      document.removeEventListener('keydown', handleKeyDown);
      trigger?.focus();
    };
  }, [panelRef, isOpen, onClose, triggerRef]);
};

/** The blue bar repeated at the top of the panel, with the close button where the menu button was. */
const MobileMenuTopBar = ({onClose}: {onClose: () => void}) => (
  <>
  <div className="header-mobile-top">
    <span className="header-mobile-ucm" aria-hidden="true">
      <ResponsiveBrandImage brand="ucm" alt="" sizes="138px" />
    </span>
    <a href="/" className="header-mobile-brand" aria-label="Innovate To Grow home">
      <ResponsiveBrandImage brand="i2g" alt="" className="header-mobile-logo" sizes="50px" />
    </a>
    {/* Drawn like the menu button it replaces (the reference keeps the three bars). */}
    <button type="button" className="header-mobile-close" aria-label="Close menu" onClick={onClose}>
      <span className="header-mobile-close-bar" />
      <span className="header-mobile-close-bar" />
      <span className="header-mobile-close-bar" />
    </button>
  </div>

  <div className="header-mobile-sitename" aria-hidden="true">
    Innovate To Grow
  </div>
  </>
);

const MobileMenuNav = ({menuItems, state, current}: Pick<MobileMenuPanelProps, 'menuItems' | 'state' | 'current'>) => (
  <nav className="header-mobile-nav" aria-label="Mobile navigation" aria-busy={state === 'loading'}>
    {state === 'loading' ? (
      <ul className="header-mobile-nav-skeleton" aria-hidden="true">
        {MENU_BAR_SKELETON_WIDTHS_PX.map((width, index) => (
          <li key={index} className="header-mobile-nav-skeleton-row">
            <span className="menu-bar-skeleton" style={{width: `${Math.min(width + 24, 200)}px`}} />
          </li>
        ))}
      </ul>
    ) : null}
    {state === 'error' ? <p className="header-mobile-nav-message">Menu unavailable</p> : null}
    {state === 'ready' && menuItems.length > 0 ? (
      <MobileMenuTree key={current?.menuIndex ?? 'none'} items={menuItems} current={current} />
    ) : null}
  </nav>
);

const MobileMenuMember = ({
  hasMemberIdentity,
  user,
  onAccountClick,
  onLoginClick,
  onLogoutClick,
}: Pick<MobileMenuPanelProps, 'hasMemberIdentity' | 'user' | 'onAccountClick' | 'onLoginClick' | 'onLogoutClick'>) => (
  <div className="header-mobile-member">
    {hasMemberIdentity ? (
      <>
        <div className="header-mobile-member-info">
          {user?.profile_image ? (
            <img src={user.profile_image} alt="" className="header-mobile-member-avatar" />
          ) : (
            <Icon name="user-circle" />
          )}
          <span>{memberDisplayName(user, formatE164ForDisplay)}</span>
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
        Sign In / Sign Up
      </button>
    )}
  </div>
);

/**
 * Phone menu dialog. It covers the viewport and repeats the blue bar at the
 * top (UC Merced wordmark, round logo, close button where the menu button
 * was) and the site name, so it reads as the reference site's menu panel
 * opening under the bar while keeping its own close control inside the modal
 * for screen-reader users. Rows, member links and the Directory / Apply / Give
 * strip follow the reference's phone menu.
 */
export const MobileMenuPanel = ({
  menuItems,
  state,
  isMobileOpen,
  hasMemberIdentity,
  user,
  current = null,
  triggerRef,
  onClose,
  onAccountClick,
  onLoginClick,
  onLogoutClick,
}: MobileMenuPanelProps) => {
  const panelRef = useRef<HTMLDivElement>(null);

  useDialogFocusTrap(panelRef, isMobileOpen, onClose, triggerRef);

  return (
    <div
      ref={panelRef}
      id="mobile-menu"
      className={`header-mobile-menu${isMobileOpen ? ' is-open' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label="Mobile menu"
      aria-hidden={!isMobileOpen}
      inert={!isMobileOpen}
      hidden={!isMobileOpen}
      tabIndex={-1}
    >
      <MobileMenuTopBar onClose={onClose} />

      <MobileMenuNav menuItems={menuItems} state={state} current={current} />

      <MobileMenuMember
        hasMemberIdentity={hasMemberIdentity}
        user={user}
        onAccountClick={onAccountClick}
        onLoginClick={onLoginClick}
        onLogoutClick={onLogoutClick}
      />

      <ul className="header-mobile-actions" aria-label="UC Merced links">
        {UNIVERSITY_LINKS.map((link) => (
          <li key={link.label}>
            <a href={link.href} target="_blank" rel="noopener noreferrer" className="header-mobile-university-link">
              {link.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
};
