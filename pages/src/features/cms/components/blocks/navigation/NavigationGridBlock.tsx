import { Link } from 'react-router';
import { safeHref } from '@/lib/security';
import {CMS_PAGE_TITLE_CLASS} from '../headings';

export interface NavigationGridItem {
  title: string;
  description?: string;
  url: string;
  is_external?: boolean;
}

export interface NavigationGridData {
  heading?: string;
  items: NavigationGridItem[];
}

export const NavigationGridBlock = ({ data }: { data: NavigationGridData }) => {
  const items = Array.isArray(data.items) ? data.items : [];

  return (
    <section className="cms-navigation-grid">
      {data.heading && <h1 className={CMS_PAGE_TITLE_CLASS}>{data.heading}</h1>}
      {items.length > 0 && (
        <ul className="cms-navigation-grid-list projects-hub-list">
          {items.map((item, i) => (
            <li key={`${item.url}-${i}`} className="cms-navigation-grid-item projects-hub-item itg-rule-panel">
              <h2 className="cms-navigation-grid-title">
                {item.is_external ? (
                  <a
                    href={safeHref(item.url)}
                    className="projects-hub-link"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {item.title}
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                ) : (
                  <Link to={item.url} className="projects-hub-link">
                    {item.title}
                  </Link>
                )}
              </h2>
              {item.description && (
                <p className="cms-navigation-grid-description">{item.description}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};
