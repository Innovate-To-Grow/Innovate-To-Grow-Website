import {useEffect, useRef, type RefObject} from 'react';
import {type MenuItem} from '@/features/layout/api';
import {type User} from '@/features/auth/api/types';
import {formatE164ForDisplay} from '@/features/auth/components/sections/internal/phoneInput';
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
  triggerRef: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onDesktopOpen: (index: number, hasChildren: boolean) => void;
  onDesktopClose: () => void;
  onDesktopToggle: (index: number, hasChildren: boolean) => void;
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

export const MobileMenuPanel = ({
  menuItems,
  state,
  isMobileOpen,
  isAuthenticated,
  user,
  openItemIndex,
  triggerRef,
  onClose,
  onDesktopOpen,
  onDesktopClose,
  onDesktopToggle,
  onAccountClick,
  onLoginClick,
  onLogoutClick,
}: MobileMenuPanelProps) => {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isMobileOpen) return;
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

      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      );
      if (!focusable.length) {
        event.preventDefault();
        panel.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (
        event.shiftKey &&
        (active === first || !panel.contains(active))
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (active === last || !panel.contains(active))
      ) {
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
  }, [isMobileOpen, onClose, triggerRef]);

  return (
    <>
      <div
        className={`header-mobile-overlay ${isMobileOpen ? 'is-open' : ''}`}
        onClick={onClose}
        aria-hidden="true"
        hidden={!isMobileOpen}
      />

      <div
        ref={panelRef}
        id="mobile-menu"
        className={`header-mobile-menu ${isMobileOpen ? 'is-open' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label="Mobile menu"
        aria-hidden={!isMobileOpen}
        inert={!isMobileOpen}
        hidden={!isMobileOpen}
        tabIndex={-1}
      >
        <div className="header-mobile-top">
          <a href="/" className="header-mobile-brand">
            <img
              src="/assets/images/i2glogo.png"
              alt="I2G"
              className="header-mobile-logo"
              width={2038}
              height={2039}
            />
            <span>Innovate To Grow</span>
          </a>
          <button
            type="button"
            className="header-mobile-close"
            aria-label="Close menu"
            onClick={onClose}
          >
            <i className="fa fa-times" />
          </button>
        </div>

        <nav
          className="header-mobile-nav"
          aria-label="Mobile navigation"
          aria-busy={state === 'loading'}
        >
          {state === 'loading' ? (
            <ul className="header-mobile-nav-skeleton" aria-hidden="true">
              {MENU_BAR_SKELETON_WIDTHS_PX.map((width, index) => (
                <li
                  key={index}
                  className="header-mobile-nav-skeleton-row"
                >
                  <span
                    className="menu-bar-skeleton"
                    style={{width: `${Math.min(width + 24, 200)}px`}}
                  />
                </li>
              ))}
            </ul>
          ) : null}
          {state === 'ready' && menuItems.length > 0 ? (
            <MenuTree
              items={menuItems}
              openItemIndex={openItemIndex}
              onDesktopOpen={onDesktopOpen}
              onDesktopClose={onDesktopClose}
              onDesktopToggle={onDesktopToggle}
            />
          ) : null}
        </nav>

        <div className="header-mobile-member">
          {isAuthenticated ? (
            <>
              <div className="header-mobile-member-info">
                {user?.profile_image ? (
                  <img
                    src={user.profile_image}
                    alt=""
                    className="header-mobile-member-avatar"
                  />
                ) : (
                  <i className="fa fa-user-circle" />
                )}
                <span>
                  {user?.email ||
                    formatE164ForDisplay(user?.phone ?? '') ||
                    'Member'}
                </span>
              </div>
              <div className="header-mobile-member-actions">
                <button
                  type="button"
                  className="header-mobile-action"
                  onClick={onAccountClick}
                >
                  Account
                </button>
                <button
                  type="button"
                  className="header-mobile-action"
                  onClick={onLogoutClick}
                >
                  Sign Out
                </button>
              </div>
            </>
          ) : (
            <button
              type="button"
              className="header-mobile-action primary"
              onClick={onLoginClick}
            >
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
          <a
            href="https://giving.ucmerced.edu/"
            target="_blank"
            rel="noopener noreferrer"
            className="header-mobile-action"
          >
            Give
          </a>
        </div>

        <div className="header-mobile-footer">
          <a
            href="https://www.ucmerced.edu"
            target="_blank"
            rel="noopener noreferrer"
          >
            <img
              src="/assets/images/ucmlogo.png"
              alt="UC Merced"
              width={230}
              height={57}
            />
          </a>
        </div>
      </div>
    </>
  );
};
