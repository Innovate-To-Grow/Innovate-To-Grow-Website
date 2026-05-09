import type { ElementType } from 'react';
import {SafeHtml} from '../../../SafeHtml/SafeHtml';

interface RichTextData {
  heading?: string;
  heading_level?: number;
  body_html: string;
}

export const RichTextBlock = ({ data }: { data: RichTextData }) => {
  const HeadingTag = `h${data.heading_level || 2}` as ElementType;

  return (
    <section className="cms-rich-text">
      {data.heading && <HeadingTag className="section-title">{data.heading}</HeadingTag>}
      <SafeHtml html={data.body_html} />
    </section>
  );
};
