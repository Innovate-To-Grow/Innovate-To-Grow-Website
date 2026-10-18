import { safeHref } from '@/lib/security';
import {CMS_PAGE_TITLE_CLASS} from '../headings';

export interface ContactInfoItem {
  label: string;
  value: string;
  type: 'email' | 'phone' | 'text' | 'url';
}

export interface ContactInfoData {
  heading?: string;
  items: ContactInfoItem[];
}

function renderValue(item: ContactInfoItem) {
  switch (item.type) {
    case 'email':
      return <a href={`mailto:${item.value}`}>{item.value}</a>;
    case 'phone':
      return <a href={`tel:${item.value}`}>{item.value}</a>;
    case 'url':
      return (
        <a href={safeHref(item.value)} target="_blank" rel="noopener noreferrer">
          {item.value}
        </a>
      );
    default:
      return <>{item.value}</>;
  }
}

export const ContactInfoBlock = ({ data }: { data: ContactInfoData }) => {
  const items = Array.isArray(data.items) ? data.items : [];

  return (
    <section className="cms-contact-info">
      {data.heading && <h1 className={CMS_PAGE_TITLE_CLASS}>{data.heading}</h1>}
      <p className="cms-contact-info-intro">
        For any questions, comments, or inquiries about the Innovate to Grow program, please reach out to us:
      </p>
      {items.length > 0 && (
        <dl className="itg-meta-box cms-contact-info-list">
          {items.map((item, i) => (
            <div key={i} className="itg-meta-item">
              <dt className="itg-meta-label">{item.label}</dt>
              <dd className="itg-meta-value">{renderValue(item)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
};
