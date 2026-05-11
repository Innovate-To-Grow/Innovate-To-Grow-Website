import { Link } from 'react-router-dom';
import { safeHref } from '../../../../shared/utils/safeHref';

interface NavItem {
  title: string;
  description?: string;
  url: string;
  is_external?: boolean;
}

interface NavigationGridData {
  heading?: string;
  items: NavItem[];
}

export const NavigationGridBlock = ({ data }: { data: NavigationGridData }) => {
  return (
    <section className="cms-navigation-grid">
      {data.heading && <h1>{data.heading}</h1>}
      <div className="projects-hub-list">
        {data.items.map((item, i) =>
          item.is_external ? (
            <p key={i} className="projects-hub-item">
              <a
                href={safeHref(item.url)}
                className="projects-hub-link"
                target="_blank"
                rel="noopener noreferrer"
              >
                {item.title}
              </a>
              {item.description && <>: {item.description}</>}
            </p>
          ) : (
            <p key={i} className="projects-hub-item">
              <Link to={item.url} className="projects-hub-link">
                {item.title}
              </Link>
              {item.description && <>: {item.description}</>}
            </p>
          ),
        )}
      </div>
    </section>
  );
};
