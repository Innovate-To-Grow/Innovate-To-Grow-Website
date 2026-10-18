import {useId, useState, type ReactElement} from 'react';
import {type MenuItem} from '@/features/layout/api';
import {Icon} from '@/components/Icon/Icon';
import {ariaCurrentFor, menuItemPath, type SectionMatch} from '@/features/layout/sections';
import {buildHref} from './shared';

type CurrentLocation = Pick<SectionMatch, 'menuIndex' | 'currentPath' | 'isExact'>;

interface MobileMenuTreeProps {
  items: MenuItem[];
  current?: CurrentLocation | null;
}

const linkTargetProps = (item: MenuItem) =>
  item.type === 'external' && item.open_in_new_tab
    ? {target: '_blank', rel: 'noopener noreferrer'}
    : {};

const renderNested = (items: MenuItem[], current: CurrentLocation | null): ReactElement => (
  <ul className="header-mobile-sublist">
    {items.map((item, index) => (
      <li key={index} className="header-mobile-subitem">
        <a
          href={buildHref(item)}
          className="header-mobile-sublink"
          aria-current={current ? ariaCurrentFor(menuItemPath(item), current) : undefined}
          {...linkTargetProps(item)}
        >
          {item.title}
        </a>
        {item.children?.length ? renderNested(item.children, current) : null}
      </li>
    ))}
  </ul>
);

/**
 * Phone menu: one 48px row per top-level item; items with children get an
 * expand button. The current section starts expanded.
 */
export const MobileMenuTree = ({items, current = null}: MobileMenuTreeProps) => {
  const baseId = useId();
  const [expandedIndex, setExpandedIndex] = useState<number | null>(() => {
    const index = current?.menuIndex;
    return index != null && items[index]?.children?.length ? index : null;
  });

  return (
    <ul className="header-mobile-list">
      {items.map((item, index) => {
        const hasChildren = Boolean(item.children?.length);
        const isExpanded = hasChildren && expandedIndex === index;
        const isCurrent = current?.menuIndex === index;
        const listId = `${baseId}-section-${index}`;
        const ariaCurrent = isCurrent && current ? (ariaCurrentFor(menuItemPath(item), current) ?? 'true') : undefined;

        return (
          <li
            key={index}
            className={`header-mobile-item${hasChildren ? ' has-children' : ''}${isExpanded ? ' is-expanded' : ''}${isCurrent ? ' is-current' : ''}`}
          >
            <div className="header-mobile-row">
              <a href={buildHref(item)} className="header-mobile-link" aria-current={ariaCurrent} {...linkTargetProps(item)}>
                {item.title}
              </a>
              {hasChildren ? (
                <button
                  type="button"
                  className="header-mobile-expand"
                  aria-expanded={isExpanded}
                  aria-controls={listId}
                  aria-label={`${item.title} pages`}
                  onClick={() => setExpandedIndex((prev) => (prev === index ? null : index))}
                >
                  <Icon name="angle-down" className="header-mobile-expand-icon" />
                </button>
              ) : null}
            </div>
            {hasChildren ? (
              <div id={listId} className="header-mobile-children" hidden={!isExpanded}>
                {renderNested(item.children, current)}
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
};
