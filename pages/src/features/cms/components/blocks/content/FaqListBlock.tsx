import {SafeHtml} from '@/components/SafeHtml/SafeHtml';
import {CMS_PAGE_TITLE_CLASS} from '../headings';

export interface FaqItem {
  question: string;
  answer_html: string;
}

export interface FaqListData {
  heading?: string;
  items: FaqItem[];
}

export const FaqListBlock = ({ data }: { data: FaqListData }) => {
  const items = Array.isArray(data.items) ? data.items : [];

  return (
    <section className="cms-faq-list">
      {data.heading && <h1 className={CMS_PAGE_TITLE_CLASS}>{data.heading}</h1>}
      <div className="cms-faq-items">
        {items.map((item, i) => (
          <div key={i} className="cms-faq-item">
            <h2 className="itg-section-title cms-faq-question">{item.question}</h2>
            <SafeHtml className="cms-prose cms-faq-answer" html={item.answer_html} />
          </div>
        ))}
      </div>
    </section>
  );
};
