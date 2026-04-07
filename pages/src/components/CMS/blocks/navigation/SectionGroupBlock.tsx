import {SafeHtml} from '../../../SafeHtml/SafeHtml';

interface Section {
  heading: string;
  heading_level?: number;
  body_html: string;
}

interface SectionGroupData {
  heading?: string;
  sections: Section[];
}

export const SectionGroupBlock: React.FC<{ data: SectionGroupData }> = ({ data }) => {
  return (
    <div className="cms-section-group">
      {data.heading && <h1 className="section-title">{data.heading}</h1>}
      {data.sections.map((section, i) => {
        const HeadingTag = `h${section.heading_level || 2}` as keyof React.JSX.IntrinsicElements;
        return (
          <section key={i}>
            <HeadingTag className="section-title">{section.heading}</HeadingTag>
            <SafeHtml html={section.body_html} />
          </section>
        );
      })}
    </div>
  );
};
