import type { ElementType } from 'react';
import {SafeHtml} from '@/components/SafeHtml/SafeHtml';
import {CMS_PAGE_TITLE_CLASS, headingClassForLevel, normalizeHeadingLevel} from '../headings';

export interface SectionGroupSection {
  heading: string;
  heading_level?: number;
  body_html: string;
}

export interface SectionGroupData {
  heading?: string;
  sections: SectionGroupSection[];
}

export const SectionGroupBlock = ({ data }: { data: SectionGroupData }) => {
  const sections = Array.isArray(data.sections) ? data.sections : [];

  return (
    <div className="cms-section-group">
      {data.heading && <h1 className={`section-title ${CMS_PAGE_TITLE_CLASS}`}>{data.heading}</h1>}
      {sections.map((section, i) => {
        const level = normalizeHeadingLevel(section.heading_level);
        const HeadingTag = `h${level}` as ElementType;
        return (
          <section key={i} className="cms-section-group-section">
            <HeadingTag className={`section-title ${headingClassForLevel(level)}`}>{section.heading}</HeadingTag>
            <SafeHtml className="cms-prose cms-section-group-body" html={section.body_html} />
          </section>
        );
      })}
    </div>
  );
};
