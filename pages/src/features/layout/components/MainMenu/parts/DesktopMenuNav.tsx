import type {SectionMatch} from '@/features/layout/sections';
import {MenuTree} from './MenuTree';
import {MENU_BAR_SKELETON_WIDTHS_PX, PHONE_MAX_WIDTH} from './shared';
import type {useMainMenuState} from '../useMainMenuState';

type MenuState = ReturnType<typeof useMainMenuState>;

interface DesktopMenuNavProps {
  menu: Pick<MenuState, 'menuItems' | 'state' | 'navIntroFade' | 'setNavIntroFade' | 'openItemIndex' | 'setOpenItemIndex'>;
  current: SectionMatch | null;
}

/** The desktop menu bar: a skeleton while loading, then the menu tree with hover/click dropdowns. */
export const DesktopMenuNav = ({menu, current}: DesktopMenuNavProps) => {
  const {menuItems, state, navIntroFade, setNavIntroFade, openItemIndex, setOpenItemIndex} = menu;

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
  );
};
