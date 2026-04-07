import {type FocusEvent, type KeyboardEvent, type ReactElement} from 'react';
import {type MenuItem} from '../../../../features/layout/api';
import {buildHref} from './shared';

interface MenuTreeProps {
  items: MenuItem[];
  openItemIndex: number | null;
  onDesktopOpen: (index: number, hasChildren: boolean) => void;
  onDesktopClose: () => void;
  onDesktopToggle: (index: number, hasChildren: boolean) => void;
}

const renderItems = (
  items: MenuItem[],
  level: number,
  openItemIndex: number | null,
  onDesktopOpen: (index: number, hasChildren: boolean) => void,
  onDesktopClose: () => void,
  onDesktopToggle: (index: number, hasChildren: boolean) => void,
): ReactElement => {
  const handleTopLevelKeyDown = (
    event: KeyboardEvent<HTMLAnchorElement>,
    index: number,
    hasChildren: boolean,
  ) => {
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

  if (level === 0) {
    return (
      <ul className="menu-bar-list">
        {items.map((item, index) => {
          const hasChildren = item.children && item.children.length > 0;
          const isOpen = openItemIndex === index;
          const href = buildHref(item);
          const isExternal = item.type === 'external';

          const accessibilityProps = hasChildren
            ? {'aria-haspopup': 'menu' as const, 'aria-expanded': isOpen}
            : {};

          return (
            <li
              key={index}
              className={`menu-bar-item${hasChildren ? ' has-children' : ''}${isOpen ? ' is-open' : ''}`}
              onMouseEnter={() => onDesktopOpen(index, hasChildren)}
              onMouseLeave={onDesktopClose}
              onFocus={() => onDesktopOpen(index, hasChildren)}
              onBlur={handleTopLevelBlur}
            >
              <a
                href={href}
                className="menu-bar-link"
                {...accessibilityProps}
                target={isExternal && item.open_in_new_tab ? '_blank' : undefined}
                rel={isExternal && item.open_in_new_tab ? 'noopener noreferrer' : undefined}
                onClick={() => (hasChildren ? onDesktopToggle(index, hasChildren) : undefined)}
                onKeyDown={(event) => handleTopLevelKeyDown(event, index, hasChildren)}
              >
                {item.icon && <i className={`fa ${item.icon}`} />}
                <span>{item.title}</span>
                {hasChildren && <i className="fa fa-angle-down menu-bar-arrow" />}
              </a>

              {hasChildren && (
                <div className={`menu-dropdown${isOpen ? ' is-open' : ''}`}>
                  {renderItems(item.children, 1, openItemIndex, onDesktopOpen, onDesktopClose, onDesktopToggle)}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <ul className={`menu-dropdown-list${level > 1 ? ' nested' : ''}`}>
      {items.map((item, index) => {
        const hasChildren = item.children && item.children.length > 0;
        const href = buildHref(item);
        const isExternal = item.type === 'external';

        return (
          <li key={index} className={`menu-dropdown-item${hasChildren ? ' has-children' : ''}`}>
            <a
              href={href}
              className="menu-dropdown-link"
              target={isExternal && item.open_in_new_tab ? '_blank' : undefined}
              rel={isExternal && item.open_in_new_tab ? 'noopener noreferrer' : undefined}
            >
              {item.icon && <i className={`fa ${item.icon}`} />}
              <span>{item.title}</span>
              {hasChildren && <i className="fa fa-angle-right menu-dropdown-arrow" />}
            </a>
            {hasChildren && (
              <div className="menu-dropdown-nested">
                {renderItems(item.children, level + 1, openItemIndex, onDesktopOpen, onDesktopClose, onDesktopToggle)}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
};

export const MenuTree = ({items, openItemIndex, onDesktopOpen, onDesktopClose, onDesktopToggle}: MenuTreeProps) =>
  renderItems(items, 0, openItemIndex, onDesktopOpen, onDesktopClose, onDesktopToggle);
