import { useEffect, useMemo, useState, type MouseEvent, type ReactElement } from 'react';
import { type MenuItem } from '../../../services/api';
import { useMenu } from '../LayoutProvider/context';
import './MainMenu.css';

const buildHref = (item: MenuItem) => {
  if (item.type === 'home') {
    return '/';
  }
  if (item.type === 'page' && item.page_slug) {
    return `/${item.page_slug}`;
  }
  if (item.type === 'external' && item.url) {
    return item.url;
  }
  return item.url || '#';
};

export const MainMenu = () => {
  const { menu, state } = useMenu();
  const [openItemIndex, setOpenItemIndex] = useState<number | null>(null);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const currentDate = useMemo(() => {
    const date = new Date();
    const days = ['SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];
    const months = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'];
    return `${days[date.getDay()]} ${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
  }, []);

  useEffect(() => {
    const handleToggle = () => {
      setIsMobileOpen(prev => !prev);
    };

    window.addEventListener('toggle-menu', handleToggle);
    return () => window.removeEventListener('toggle-menu', handleToggle);
  }, []);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth > 992 && isMobileOpen) {
        setIsMobileOpen(false);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [isMobileOpen]);

  // Lock body scroll when mobile menu is open
  useEffect(() => {
    if (isMobileOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isMobileOpen]);

  const toggleMobileMenu = () => setIsMobileOpen(prev => !prev);

  const handleToggle = (index: number, hasChildren: boolean, event: MouseEvent) => {
    if (!hasChildren) return;

    const isMobile = window.innerWidth <= 992;
    if (!isMobile) {
      return;
    }

    event.preventDefault();
    setOpenItemIndex(prev => (prev === index ? null : index));
  };

  const handleMouseEnter = (index: number, hasChildren: boolean) => {
    if (window.innerWidth > 992 && hasChildren) {
      setOpenItemIndex(index);
    }
  };

  const handleMouseLeave = () => {
    if (window.innerWidth > 992) {
      setOpenItemIndex(null);
    }
  };

  const renderMenuItems = (items: MenuItem[], level: number = 0): ReactElement => {
    if (level === 0) {
      return (
        <ul className="menu-bar-list">
          {items.map((item, index) => {
            const hasChildren = item.children && item.children.length > 0;
            const isOpen = openItemIndex === index;
            const href = buildHref(item);
            const isExternal = item.type === 'external';

            const accessibilityProps = hasChildren
              ? {
                  'aria-haspopup': 'menu' as const,
                }
              : {};

            return (
              <li
                key={index}
                className={`menu-bar-item${hasChildren ? ' has-children' : ''}${isOpen ? ' is-open' : ''}`}
                onMouseEnter={() => handleMouseEnter(index, hasChildren)}
                onMouseLeave={handleMouseLeave}
              >
                <a
                  href={href}
                  className="menu-bar-link"
                  {...accessibilityProps}
                  target={isExternal && item.open_in_new_tab ? '_blank' : undefined}
                  rel={isExternal && item.open_in_new_tab ? 'noopener noreferrer' : undefined}
                  onClick={(e) => hasChildren ? handleToggle(index, hasChildren, e) : undefined}
                >
                  {item.icon && <i className={`fa ${item.icon}`}></i>}
                  <span>{item.title}</span>
                  {hasChildren && <i className="fa fa-angle-down menu-bar-arrow" />}
                </a>

                {hasChildren && (
                  <div className={`menu-dropdown${isOpen ? ' is-open' : ''}`}>
                    {renderMenuItems(item.children, 1)}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      );
    } else {
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
                  {item.icon && <i className={`fa ${item.icon}`}></i>}
                  <span>{item.title}</span>
                  {hasChildren && <i className="fa fa-angle-right menu-dropdown-arrow" />}
                </a>
                {hasChildren && (
                  <div className="menu-dropdown-nested">
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
    <header className="site-header" role="banner">
      {/* Top blue bar */}
      <div className="site-header-top">
        <div className="site-header-container site-header-top-inner">
          {/* Mobile Menu Toggle (shown on small screens) */}
          <button
            type="button"
            className={`site-header-mobile-toggle ${isMobileOpen ? 'is-active' : ''}`}
            aria-label="Toggle menu"
            aria-controls="mobile-menu"
            onClick={toggleMobileMenu}
          >
            <span className="site-header-mobile-toggle-bar" />
            <span className="site-header-mobile-toggle-bar" />
            <span className="site-header-mobile-toggle-bar" />
          </button>

          <a
            className="ucm-wordmark"
            href="https://www.ucmerced.edu"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="UC Merced"
          >
            <img src="/static/images/ucmlogo.png" alt="UC Merced" />
          </a>

          <a className="site-header-top-logo" href="/" aria-label="Innovate To Grow">
            <img
              className="site-header-top-logo-full"
              src="/static/images/I2G-fullname-low.png"
              alt="Innovate To Grow"
            />
          </a>

          <div className="site-header-top-links" aria-label="Quick links">
            <a href="https://directory.ucmerced.edu/" target="_blank" rel="noopener noreferrer">
              Directory
            </a>
            <a href="https://admissions.ucmerced.edu/first-year/apply?button" target="_blank" rel="noopener noreferrer">
              Apply
            </a>
            <a href="http://giving.ucmerced.edu/" target="_blank" rel="noopener noreferrer">
              Give
            </a>
          </div>
        </div>
      </div>

      {/* White menu bar */}
      <div className="site-header-bottom">
        <div className="site-header-container site-header-bottom-inner">
          <div className="site-header-bottom-left">
            <a className="site-header-badge" href="/" aria-label="Home">
              <img src="/static/images/i2glogo.png" alt="Innovate To Grow" />
            </a>

            <nav className="site-header-nav" aria-label="Main menu">
              {state === 'loading' && (
                <ul className="menu-bar-list">
                  <li className="menu-bar-item is-muted">
                    <span className="menu-bar-link">Loading...</span>
                  </li>
                </ul>
              )}

              {state === 'error' && (
                <ul className="menu-bar-list">
                  <li className="menu-bar-item is-error">
                    <span className="menu-bar-link">Menu unavailable</span>
                  </li>
                </ul>
              )}

              {state === 'ready' && menu && menu.items && menu.items.length > 0 && renderMenuItems(menu.items)}

              {state === 'ready' && (!menu || !menu.items || menu.items.length === 0) && (
                <ul className="menu-bar-list">
                  <li className="menu-bar-item is-muted">
                    <span className="menu-bar-link">No menu items</span>
                  </li>
                </ul>
              )}
            </nav>
          </div>

          <div className="site-header-date" aria-label="Current date">
            {currentDate}
          </div>
        </div>
      </div>

      {/* Mobile Menu Overlay */}
      <div 
        className={`header-mobile-overlay ${isMobileOpen ? 'is-open' : ''}`}
        onClick={toggleMobileMenu}
        aria-hidden="true"
      />

      {/* Mobile Menu Panel */}
      <div 
        id="mobile-menu"
        className={`header-mobile-menu ${isMobileOpen ? 'is-open' : ''}`}
        aria-label="Mobile menu"
      >
        <div className="header-mobile-top">
          <a href="/" className="header-mobile-brand">
            <img src="/static/images/i2glogo.png" alt="I2G" className="header-mobile-logo" />
            <span>Innovate To Grow</span>
          </a>
          <button
            type="button"
            className="header-mobile-close"
            aria-label="Close menu"
            onClick={toggleMobileMenu}
          >
            <i className="fa fa-times" />
          </button>
        </div>

        <nav className="header-mobile-nav">
          {state === 'ready' && menu && menu.items && menu.items.length > 0 && renderMenuItems(menu.items)}
        </nav>

        <div className="header-mobile-actions">
          <a 
            href="https://directory.ucmerced.edu/" 
            target="_blank" 
            rel="noopener noreferrer"
            className="header-mobile-action"
          >
            <i className="fa fa-search" />
            Directory
          </a>
          <a 
            href="https://admissions.ucmerced.edu/first-year/apply?button" 
            target="_blank" 
            rel="noopener noreferrer"
            className="header-mobile-action primary"
          >
            <i className="fa fa-edit" />
            Apply Now
          </a>
          <a 
            href="http://giving.ucmerced.edu/" 
            target="_blank" 
            rel="noopener noreferrer"
            className="header-mobile-action"
          >
            <i className="fa fa-heart" />
            Give
          </a>
        </div>

        <div className="header-mobile-footer">
          <a href="https://www.ucmerced.edu" target="_blank" rel="noopener noreferrer">
            <img 
              src="/static/images/ucmlogo.png"
              alt="UC Merced" 
            />
          </a>
        </div>
      </div>
    </header>
  );
};
