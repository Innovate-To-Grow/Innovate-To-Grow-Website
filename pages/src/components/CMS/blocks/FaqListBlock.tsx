interface FaqItem {
  question: string;
  answer_html: string;
}

interface FaqListData {
  heading?: string;
  items: FaqItem[];
}

export const FaqListBlock: React.FC<{ data: FaqListData }> = ({ data }) => {
  return (
    <section className="cms-faq-list">
      {data.heading && <h1 className="faq-page-title">{data.heading}</h1>}
      <div className="faq-content">
        {data.items.map((item, i) => (
          <div key={i}>
            <h2 className="faq-question">{item.question}</h2>
            <div dangerouslySetInnerHTML={{ __html: item.answer_html }} />
          </div>
        ))}
      </div>
    </section>
  );
};
