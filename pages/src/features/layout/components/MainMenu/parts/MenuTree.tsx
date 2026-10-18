import {type FocusEvent, type KeyboardEvent, type ReactElement} from 'react';
import {type MenuItem} from '@/features/layout/api';
import {Icon} from '@/components/Icon/Icon';
import {ariaCurrentFor, menuItemPath, type SectionMatch} from '@/features/layout/sections';
import {buildHref} from './shared';

type CurrentLocation = Pick<SectionMatch, 'menuIndex' | 'currentPath' | 'isExact'>;

interface MenuTreeProps {
  items: MenuItem[];
  openItemIndex: number | null;
  /** Current section + page, used for the gold underline and aria-current. */
  current?: CurrentLocation | null;
  onDesktopOpen: (index: number, hasChildren: boolean) => void;
  onDesktopClose: () => void;
  onDesktopToggle: (index: number, hasChildren: boolean) => void;
}

const linkTargetProps = (item: MenuItem) =>
  item.type === 'external' && item.open_in_new_tab
    ? {target: '_blank', rel: 'noopener noreferrer'}
    : {};

const renderDropdownItems = (items: MenuItem[], level: number, current: CurrentLocation | null): ReactElement => (
  <ul className={`menu-dropdown-list${level > 1 ? ' nested' : ''}`}>
    {items.map((item, index) => {
      const hasChildren = Boolean(item.children?.length);
      const ariaCurrent = current ? ariaCurrentFor(menuItemPath(item), current) : undefined;

      return (
        <li key={index} className={`menu-dropdown-item${hasChildren ? ' has-children' : ''}`}>
          <a href={buildHref(item)} className="menu-dropdown-link" aria-current={ariaCurrent} {...linkTargetProps(item)}>
            {item.icon && <Icon name={item.icon} className="menu-icon" />}
            <span>{item.title}</span>
            {hasChildren && <Icon name="angle-right" className="menu-dropdown-arrow" />}
          </a>
          {hasChildren && (
            <div className="menu-dropdown-nested">{renderDropdownItems(item.children, level + 1, current)}</div>
          )}
        </li>
      );
    })}
  </ul>
);

export const MenuTree = ({
  items,
  openItemIndex,
  current = null,
  onDesktopOpen,
  onDesktopClose,
  onDesktopToggle,
}: MenuTreeProps) => {
  const handleTopLevelKeyDown = (event: KeyboardEvent<HTMLAnchorElement>, index: number, hasChildren: boolean) => {
    if (!hasChildren) {
      return;
    }

    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onDesktopOpen(index, true);
      const firstChildLink = event.currentTarget.parentElement?.querySelector('.menu-dropdown a') as HTMLAnchorElement | null;
      firstChildLink?.focus();
      return;
    }

    if (event.key === 'Escape') {
      event.preventDefault();
      onDesktopClose();
      event.currentTarget.blur();
    }
  };

  const handleTopLevelBlur = (event: FocusEvent<HTMLLIElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      onDesktopClose();
    }
  };

  return (
    <ul className="menu-bar-list">
      {items.map((item, index) => {
        const hasChildren = Boolean(item.children?.length);
        const isOpen = openItemIndex === index;
        const isCurrent = current?.menuIndex === index;
        // The section item is "current" even on a child page; it is the page
        // itself only when its own URL is the current path.
        const ariaCurrent = isCurrent && current ? (ariaCurrentFor(menuItemPath(item), current) ?? 'true') : undefined;

        const accessibilityProps = hasChildren
          ? {'aria-haspopup': 'menu' as const, 'aria-expanded': isOpen}
          : {};

        return (
          <li
            key={index}
            className={`menu-bar-item${hasChildren ? ' has-children' : ''}${isOpen ? ' is-open' : ''}${isCurrent ? ' is-current' : ''}`}
            onMouseEnter={() => onDesktopOpen(index, hasChildren)}
            onMouseLeave={onDesktopClose}
            onFocus={() => onDesktopOpen(index, hasChildren)}
            onBlur={handleTopLevelBlur}
          >
            <a
              href={buildHref(item)}
              className="menu-bar-link"
              aria-current={ariaCurrent}
              {...accessibilityProps}
              {...linkTargetProps(item)}
              onClick={() => (hasChildren ? onDesktopToggle(index, hasChildren) : undefined)}
              onKeyDown={(event) => handleTopLevelKeyDown(event, index, hasChildren)}
            >
              {item.icon && <Icon name={item.icon} className="menu-icon" />}
              <span>{item.title}</span>
            </a>

            {hasChildren && (
              <div className={`menu-dropdown${isOpen ? ' is-open' : ''}`}>
                {renderDropdownItems(item.children, 1, current)}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
};
