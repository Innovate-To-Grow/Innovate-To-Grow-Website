import type { ElementType } from 'react';
import {SafeHtml} from '@/components/SafeHtml/SafeHtml';
import {headingClassForLevel, normalizeHeadingLevel} from '../headings';

export interface RichTextData {
  heading?: string;
  heading_level?: number;
  body_html: string;
}

export const RichTextBlock = ({ data }: { data: RichTextData }) => {
  const level = normalizeHeadingLevel(data.heading_level);
  const HeadingTag = `h${level}` as ElementType;

  return (
    <section className="cms-rich-text">
      {data.heading && (
        <HeadingTag className={`section-title ${headingClassForLevel(level)}`}>{data.heading}</HeadingTag>
      )}
      <SafeHtml className="cms-prose cms-rich-text-body" html={data.body_html} />
    </section>
  );
};
