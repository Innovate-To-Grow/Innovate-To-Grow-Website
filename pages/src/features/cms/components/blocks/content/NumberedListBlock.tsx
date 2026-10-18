import { SafeHtml } from '@/components/SafeHtml/SafeHtml';

export interface NumberedListData {
  heading?: string;
  /** Intro HTML shown above the list (sanitized like every other block body). */
  preamble_html?: string;
  /** Plain-text steps, one string per item, as the admin block editor stores them. */
  items: string[];
}

function itemText(item: unknown): string {
  if (typeof item === 'string') return item.trim();
  if (typeof item === 'number') return String(item);
  return '';
}

export const NumberedListBlock = ({ data }: { data: NumberedListData }) => {
  const items = (Array.isArray(data.items) ? data.items : []).map(itemText).filter(Boolean);
  const heading = typeof data.heading === 'string' ? data.heading.trim() : '';
  const preamble = typeof data.preamble_html === 'string' ? data.preamble_html : '';

  return (
    <section className="cms-numbered-list">
      {heading && <h2 className="section-title itg-section-title">{heading}</h2>}
      <div className="cms-prose cms-numbered-list-body">
        {preamble.trim() && <SafeHtml className="cms-numbered-list-preamble" html={preamble} />}
        {items.length > 0 && (
          <ol className="cms-numbered-list-items">
            {items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
};
