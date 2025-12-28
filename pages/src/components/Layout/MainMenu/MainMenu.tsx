import { useEffect, useState, type MouseEvent, type ReactElement } from 'react';
import { type MenuItem } from '../../../services/api';
import { useMenu } from '../LayoutProvider/LayoutProvider';
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
        <ul className="header-nav-list">
          {items.map((item, index) => {
            const hasChildren = item.children && item.children.length > 0;
            const isOpen = openItemIndex === index;
            const href = buildHref(item);
            const isExternal = item.type === 'external';

            const accessibilityProps = hasChildren
              ? {
                  'aria-haspopup': 'menu' as const,
                  'aria-expanded': isOpen ? ('true' as const) : ('false' as const),
                }
              : {};

            return (
              <li
                key={index}
                className={`header-nav-item${hasChildren ? ' has-children' : ''}${isOpen ? ' is-open' : ''}`}
                onMouseEnter={() => handleMouseEnter(index, hasChildren)}
                onMouseLeave={handleMouseLeave}
              >
                <a
                  href={href}
                  className="header-nav-link"
                  {...accessibilityProps}
                  target={isExternal && item.open_in_new_tab ? '_blank' : undefined}
                  rel={isExternal && item.open_in_new_tab ? 'noopener noreferrer' : undefined}
                  onClick={(e) => hasChildren ? handleToggle(index, hasChildren, e) : undefined}
                >
                  {item.icon && <i className={`fa ${item.icon}`}></i>}
                  <span>{item.title}</span>
                  {hasChildren && <i className="fa fa-angle-down header-nav-arrow" />}
                </a>

                {hasChildren && (
                  <div className={`header-dropdown${isOpen ? ' is-open' : ''}`}>
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
        <ul className={`header-dropdown-list${level > 1 ? ' nested' : ''}`}>
          {items.map((item, index) => {
            const hasChildren = item.children && item.children.length > 0;
            const href = buildHref(item);
            const isExternal = item.type === 'external';

            return (
              <li key={index} className={`header-dropdown-item${hasChildren ? ' has-children' : ''}`}>
                <a
                  href={href}
                  className="header-dropdown-link"
                  target={isExternal && item.open_in_new_tab ? '_blank' : undefined}
                  rel={isExternal && item.open_in_new_tab ? 'noopener noreferrer' : undefined}
                >
                  {item.icon && <i className={`fa ${item.icon}`}></i>}
                  <span>{item.title}</span>
                  {hasChildren && <i className="fa fa-angle-right header-dropdown-arrow" />}
                </a>
                {hasChildren && (
                  <div className="header-dropdown-nested">
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
      <div className="header-inner">
        {/* Logo & Branding */}
        <a href="/" className="header-brand">
          <img 
            src="/static/images/i2glogo.png" 
            alt="" 
            className="header-logo"
          />
          <div className="header-titles">
            <span className="header-title">Innovate To Grow</span>
            <span className="header-subtitle">UC Merced · School of Engineering</span>
          </div>
        </a>

        {/* Desktop Navigation */}
        <nav className="header-nav" aria-label="Main menu">
          {state === 'loading' && (
            <ul className="header-nav-list">
              <li className="header-nav-item is-muted">
                <span className="header-nav-link">Loading...</span>
              </li>
            </ul>
          )}

          {state === 'error' && (
            <ul className="header-nav-list">
              <li className="header-nav-item is-error">
                <span className="header-nav-link">Menu unavailable</span>
              </li>
            </ul>
          )}

          {state === 'ready' && menu && menu.items && menu.items.length > 0 && renderMenuItems(menu.items)}

          {state === 'ready' && (!menu || !menu.items || menu.items.length === 0) && (
            <ul className="header-nav-list">
              <li className="header-nav-item is-muted">
                <span className="header-nav-link">No menu items</span>
              </li>
            </ul>
          )}
        </nav>

        {/* Quick Links */}
        <div className="header-actions">
          <a 
            href="https://directory.ucmerced.edu/" 
            target="_blank" 
            rel="noopener noreferrer"
            className="header-action-link"
          >
            <i className="fa fa-search" />
            <span>Directory</span>
          </a>
          <a 
            href="https://admissions.ucmerced.edu/first-year/apply?button" 
            target="_blank" 
            rel="noopener noreferrer"
            className="header-action-btn"
          >
            Apply
          </a>
        </div>

        {/* Mobile Menu Toggle */}
        <button
          type="button"
          className={`header-menu-toggle ${isMobileOpen ? 'is-active' : ''}`}
          aria-label="Toggle menu"
          aria-controls="mobile-menu"
          aria-expanded={isMobileOpen || undefined}
          onClick={toggleMobileMenu}
        >
          <span className="header-menu-toggle-bar" />
          <span className="header-menu-toggle-bar" />
          <span className="header-menu-toggle-bar" />
        </button>
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
              src="https://innovatetogrow.ucmerced.edu/sites/all/themes/UCMerced/ucmlogo.png" 
              alt="UC Merced" 
            />
          </a>
        </div>
      </div>
    </header>
  );
};
