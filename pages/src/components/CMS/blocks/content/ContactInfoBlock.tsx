interface ContactItem {
  label: string;
  value: string;
  type: 'email' | 'phone' | 'text' | 'url';
}

interface ContactInfoData {
  heading?: string;
  items: ContactItem[];
}

function renderValue(item: ContactItem) {
  switch (item.type) {
    case 'email':
      return <a href={`mailto:${item.value}`}>{item.value}</a>;
    case 'phone':
      return <a href={`tel:${item.value}`}>{item.value}</a>;
    case 'url':
      return (
        <a href={item.value} target="_blank" rel="noopener noreferrer">
          {item.value}
        </a>
      );
    default:
      return <>{item.value}</>;
  }
}

export const ContactInfoBlock: React.FC<{ data: ContactInfoData }> = ({ data }) => {
  return (
    <section className="cms-contact-info">
      {data.heading && <h1 className="contact-page-title">{data.heading}</h1>}
      <p className="contact-text">
        For any questions, comments, or inquiries about the Innovate to Grow program, please reach out to us:
      </p>
      {data.items.map((item, i) => (
        <p key={i} className="contact-text">
          <strong>{item.label}:</strong> {renderValue(item)}
        </p>
      ))}
    </section>
  );
};
