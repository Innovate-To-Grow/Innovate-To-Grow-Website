import { useEffect, useState, type MouseEvent } from 'react';
import { getCachedMenus, type Menu, type MenuItem } from '../../services/menu';
import './MainMenu.css';

type LoadState = 'loading' | 'ready' | 'error';

const buildHref = (item: MenuItem) => {
  if (item.type === 'home') {
    return '/';
  }
  if (item.type === 'page' && item.page_slug) {
    return `/pages/${item.page_slug}`;
  }
  if (item.type === 'external' && item.url) {
    return item.url;
  }
  return item.url || '#';
};

const formatDate = (date: Date) => {
  const days = ['SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];
  const months = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'];
  return `${days[date.getDay()]} ${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
};

export const MainMenu = () => {
  const [menu, setMenu] = useState<Menu | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [openItemIndex, setOpenItemIndex] = useState<number | null>(null);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [currentDate] = useState(formatDate(new Date()));

  useEffect(() => {
    const loadMenus = async () => {
      try {
        const menus = await getCachedMenus();
        // Get the first menu (main navigation)
        if (menus.length > 0) {
          setMenu(menus[0]);
        }
        setState('ready');
      } catch (error) {
        console.error('Failed to load menus', error);
        setState('error');
      }
    };
    loadMenus();

    const handleToggle = () => {
      setIsMobileOpen(prev => !prev);
    };

    window.addEventListener('toggle-menu', handleToggle);
    return () => window.removeEventListener('toggle-menu', handleToggle);
  }, []);

  const handleToggle = (index: number, hasChildren: boolean, event: MouseEvent) => {
    if (!hasChildren) return;
    event.preventDefault();
    setOpenItemIndex(prev => (prev === index ? null : index));
  };

  const handleMouseEnter = (index: number, hasChildren: boolean) => {
    if (window.innerWidth > 768 && hasChildren) {
      setOpenItemIndex(index);
    }
  };

  const handleMouseLeave = () => {
    if (window.innerWidth > 768) {
      setOpenItemIndex(null);
    }
  };

  // Recursive function to render menu items with nested children
  const renderMenuItems = (items: MenuItem[], level: number = 0): JSX.Element => {
    if (level === 0) {
      // Top-level menu items
      return (
        <ul className="menu-list">
          {items.map((item, index) => {
            const hasChildren = item.children && item.children.length > 0;
            const isOpen = openItemIndex === index;
            const href = buildHref(item);
            const isExternal = item.type === 'external';

            return (
              <li
                key={index}
                className={`menu-item${hasChildren ? ' has-children' : ''}${isOpen ? ' submenu-open' : ''}`}
                onMouseEnter={() => handleMouseEnter(index, hasChildren)}
                onMouseLeave={handleMouseLeave}
              >
                <a
                  href={href}
                  className="menu-link"
                  aria-haspopup={hasChildren ? 'menu' : undefined}
                  aria-expanded={hasChildren ? (isOpen ? 'true' : 'false') : undefined}
                  target={isExternal && item.open_in_new_tab ? '_blank' : undefined}
                  rel={isExternal && item.open_in_new_tab ? 'noopener noreferrer' : undefined}
                  onClick={(e) => hasChildren ? handleToggle(index, hasChildren, e) : undefined}
                >
                  {item.icon && <i className={`fa ${item.icon}`}></i>}
                  {item.title}
                </a>

                {hasChildren && (
                  <div className={`menu-sub-wrapper${isOpen ? ' open' : ''}`}>
                    {renderMenuItems(item.children, 1)}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      );
    } else {
      // Submenu items (level 1 and deeper)
      return (
        <ul className={`menu-sub${level > 1 ? ' menu-sub-nested' : ''}`}>
          {items.map((item, index) => {
            const hasChildren = item.children && item.children.length > 0;
            const href = buildHref(item);
            const isExternal = item.type === 'external';

            return (
              <li key={index} className={`menu-sub-item${hasChildren ? ' has-children' : ''}`}>
                <a
                  href={href}
                  target={isExternal && item.open_in_new_tab ? '_blank' : undefined}
                  rel={isExternal && item.open_in_new_tab ? 'noopener noreferrer' : undefined}
                >
                  {item.icon && <i className={`fa ${item.icon}`}></i>}
                  {item.title}
                  {hasChildren && <span className="menu-arrow">›</span>}
                </a>
                {hasChildren && (
                  <div className="menu-sub-nested-wrapper">
                    {renderMenuItems(item.children, level + 1)}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      );
    }
  };

  return (
    <nav className={`menu-shell ${isMobileOpen ? 'mobile-open' : ''}`} aria-label="Main menu">
      <div className="menu-inner">
        <div className="menu-left">
          <div className="menu-logo">
            <a href="/" aria-label="Innovate to Grow">
              <img src="/static/images/i2glogo.png" alt="Innovate to Grow logo" />
            </a>
          </div>

          {state === 'loading' && (
            <ul className="menu-list">
              <li className="menu-item menu-muted">Loading...</li>
            </ul>
          )}

          {state === 'error' && (
            <ul className="menu-list">
              <li className="menu-item menu-error">Menu unavailable</li>
            </ul>
          )}

          {state === 'ready' && menu && menu.items && menu.items.length > 0 && renderMenuItems(menu.items)}
          
          {state === 'ready' && (!menu || !menu.items || menu.items.length === 0) && (
            <ul className="menu-list">
              <li className="menu-item menu-muted">No menu items configured</li>
            </ul>
          )}
        </div>

        <div className="menu-date">
          {currentDate}
        </div>
      </div>
    </nav>
  );
};
