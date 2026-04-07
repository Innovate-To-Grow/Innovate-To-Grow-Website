import {SafeHtml} from '../../../SafeHtml/SafeHtml';

interface RichTextData {
  heading?: string;
  heading_level?: number;
  body_html: string;
}

export const RichTextBlock: React.FC<{ data: RichTextData }> = ({ data }) => {
  const HeadingTag = `h${data.heading_level || 2}` as keyof React.JSX.IntrinsicElements;

  return (
    <section className="cms-rich-text">
      {data.heading && <HeadingTag className="section-title">{data.heading}</HeadingTag>}
      <SafeHtml html={data.body_html} />
    </section>
  );
};
