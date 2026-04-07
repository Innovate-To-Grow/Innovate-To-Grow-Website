import {SafeHtml} from '../../../SafeHtml/SafeHtml';

interface ImageTextData {
  heading?: string;
  image_url?: string;
  image_alt?: string;
  image_position?: 'top' | 'left' | 'right';
  body_html: string;
}

export const ImageTextBlock: React.FC<{ data: ImageTextData }> = ({ data }) => {
  return (
    <section className="cms-image-text">
      {data.heading && <h1 className="section-title">{data.heading}</h1>}
      <div className="capstone-content">
        {data.image_url && (
          <img
            src={data.image_url}
            alt={data.image_alt || ''}
            className="capstone-hero-image"
            loading="lazy"
          />
        )}
        <SafeHtml html={data.body_html} />
      </div>
    </section>
  );
};
