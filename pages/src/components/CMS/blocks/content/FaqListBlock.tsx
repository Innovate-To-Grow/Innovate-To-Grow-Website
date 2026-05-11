import {SafeHtml} from '../../../SafeHtml/SafeHtml';

interface FaqItem {
  question: string;
  answer_html: string;
}

interface FaqListData {
  heading?: string;
  items: FaqItem[];
}

export const FaqListBlock = ({ data }: { data: FaqListData }) => {
  return (
    <section className="cms-faq-list">
      {data.heading && <h1>{data.heading}</h1>}
      <div>
        {data.items.map((item, i) => (
          <div key={i}>
            <h2>{item.question}</h2>
            <SafeHtml html={item.answer_html} />
          </div>
        ))}
      </div>
    </section>
  );
};
