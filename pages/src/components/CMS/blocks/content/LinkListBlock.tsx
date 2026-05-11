import { Link } from 'react-router-dom';
import { safeHref } from '../../../../shared/utils/safeHref';

interface LinkItem {
  label: string;
  url: string;
  description?: string;
  is_external?: boolean;
}

interface LinkListData {
  heading?: string;
  style?: 'list' | 'grid' | 'inline';
  items: LinkItem[];
}

export const LinkListBlock = ({ data }: { data: LinkListData }) => {
  return (
    <section className="cms-link-list">
      {data.heading && <h2 className="section-title">{data.heading}</h2>}
      <ul className="cms-link-list-items">
        {data.items.map((item, i) => (
          <li key={i}>
            {item.is_external ? (
              <a href={safeHref(item.url)} target="_blank" rel="noopener noreferrer">
                {item.label}
              </a>
            ) : (
              <Link to={item.url}>{item.label}</Link>
            )}
            {item.description && <> — {item.description}</>}
          </li>
        ))}
      </ul>
    </section>
  );
};
