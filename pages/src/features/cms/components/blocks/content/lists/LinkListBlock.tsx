import { Link } from 'react-router';
import { safeHref } from '@/lib/security';

export interface LinkItem {
  label: string;
  url: string;
  description?: string;
  is_external?: boolean;
}

export interface LinkListData {
  heading?: string;
  style?: 'list' | 'grid' | 'inline';
  items: LinkItem[];
}

const LINK_LIST_STYLES = new Set(['list', 'grid', 'inline']);

export const LinkListBlock = ({ data }: { data: LinkListData }) => {
  const items = Array.isArray(data.items) ? data.items : [];
  const style = data.style && LINK_LIST_STYLES.has(data.style) ? data.style : 'list';

  return (
    <section className="cms-link-list">
      {data.heading && <h2 className="section-title itg-section-title">{data.heading}</h2>}
      <ul className={`cms-link-list-items cms-link-list-items--${style}`}>
        {items.map((item, i) => (
          <li key={i} className="cms-link-list-item">
            {item.is_external ? (
              <a href={safeHref(item.url)} target="_blank" rel="noopener noreferrer">
                {item.label}
              </a>
            ) : (
              <Link to={item.url}>{item.label}</Link>
            )}
            {item.description && <span className="cms-link-list-description"> — {item.description}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
};
