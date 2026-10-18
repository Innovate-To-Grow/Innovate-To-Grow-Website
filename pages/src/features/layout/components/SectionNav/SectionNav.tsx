import {useId, type ReactNode} from 'react';
import {Link, useNavigate} from 'react-router';
import {type MenuItem} from '@/features/layout/api';
import {safeHref} from '@/lib/security';
import {ariaCurrentFor, menuItemPath, sectionOptions, type SectionMatch} from '@/features/layout/sections';

type CurrentPage = Pick<SectionMatch, 'currentPath' | 'isExact'>;

interface SectionNavProps {
  section: MenuItem;
  current: CurrentPage;
}

const opensNewTab = (item: MenuItem) => item.type === 'external' && item.open_in_new_tab;

/** Same-origin pages go through the router; anything else is a plain link. */
const SectionLink = ({
  item,
  current,
  className,
  children,
}: {
  item: MenuItem;
  current: CurrentPage;
  className: string;
  children: ReactNode;
}) => {
  const path = menuItemPath(item);
  const ariaCurrent = ariaCurrentFor(path, current);
  const href = safeHref(item.url);
  if (path && href.startsWith('/') && !opensNewTab(item)) {
    return (
      <Link to={href} className={className} aria-current={ariaCurrent}>
        {children}
      </Link>
    );
  }
  return (
    <a
      href={href}
      className={className}
      aria-current={ariaCurrent}
      target={opensNewTab(item) ? '_blank' : undefined}
      rel={opensNewTab(item) ? 'noopener noreferrer' : undefined}
    >
      {children}
    </a>
  );
};

const SectionList = ({items, current, level}: {items: MenuItem[]; current: CurrentPage; level: number}) => (
  <ul className={`section-nav-list${level > 0 ? ' section-nav-list--nested' : ''}`}>
    {items.map((item, index) => (
      <li key={`${item.url}-${index}`} className="section-nav-item">
        <SectionLink item={item} current={current} className="section-nav-link">
          {item.title}
        </SectionLink>
        {item.children?.length ? <SectionList items={item.children} current={current} level={level + 1} /> : null}
      </li>
    ))}
  </ul>
);

/** Desktop sidebar: the pages of the current section (hidden at phone widths by the container sheet). */
export const SectionNav = ({section, current}: SectionNavProps) => (
  <div className="section-nav">
    <nav className="section-nav-panel" aria-label={section.title}>
      <h2 className="section-nav-title">
        {menuItemPath(section) || section.url ? (
          <SectionLink item={section} current={current} className="section-nav-title-link">
            {section.title}
          </SectionLink>
        ) : (
          section.title
        )}
      </h2>
      <SectionList items={section.children} current={current} level={0} />
    </nav>
  </div>
);

/** Phone replacement for the sidebar: a labelled select that navigates to the chosen page. */
export const SectionSelect = ({section, current}: SectionNavProps) => {
  const navigate = useNavigate();
  const selectId = useId();
  const options = sectionOptions(section);
  const selectedIndex = options.findIndex((option) => option.path !== null && option.path === current.currentPath);

  const handleChange = (value: string) => {
    const option = options[Number(value)];
    if (!option) return;
    const href = safeHref(option.item.url);
    if (href === '#') return;
    if (opensNewTab(option.item)) {
      window.open(href, '_blank', 'noopener,noreferrer');
    } else if (option.path && href.startsWith('/')) {
      void navigate(href);
    } else {
      window.location.assign(href);
    }
  };

  return (
    <div className="section-nav-select">
      <label className="section-nav-select-label" htmlFor={selectId}>
        In {section.title}
      </label>
      <select
        id={selectId}
        className="section-nav-select-control"
        value={selectedIndex >= 0 ? String(selectedIndex) : ''}
        onChange={(event) => handleChange(event.target.value)}
      >
        {selectedIndex < 0 ? (
          <option value="" disabled>
            Choose a page
          </option>
        ) : null}
        {options.map((option, index) => (
          <option key={`${option.item.url}-${index}`} value={String(index)}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
};
