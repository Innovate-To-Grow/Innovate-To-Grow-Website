import { CMS_PAGE_TITLE_CLASS } from '../headings';
import { LOCAL_IMAGE_SIZES, localImageVariant } from '../localImages';

export interface HeroData {
  heading?: string;
  subheading?: string;
  image_url?: string;
  image_alt?: string;
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

/**
 * Page opener in the main column: the page title (h1), an optional lead
 * paragraph and an optional image under it. There is no full-bleed band; the
 * layout shell owns the page width.
 */
export const HeroBlock = ({
  data,
  priority = false,
}: {
  data: HeroData;
  priority?: boolean;
}) => {
  const heading = text(data.heading);
  const subheading = text(data.subheading);
  const imageUrl = text(data.image_url);
  if (!heading && !subheading && !imageUrl) return null;

  const localImage = localImageVariant(imageUrl);
  // A lead (the theme's .lead, closed by a navy rule) follows the title directly;
  // without one the title keeps the CMS page-title spacing.
  const titleClass = subheading ? 'itg-page-title cms-hero-title' : `${CMS_PAGE_TITLE_CLASS} cms-hero-title`;

  return (
    <section className="cms-hero">
      {heading && <h1 className={titleClass}>{heading}</h1>}
      {subheading && <p className="itg-lead cms-hero-lead">{subheading}</p>}
      {imageUrl && (
        <img
          src={localImage?.src ?? imageUrl}
          srcSet={localImage?.srcSet}
          sizes={localImage ? LOCAL_IMAGE_SIZES : undefined}
          width={localImage?.width}
          height={localImage?.height}
          alt={text(data.image_alt)}
          className="cms-hero-image"
          loading={priority ? 'eager' : 'lazy'}
          decoding="async"
          fetchPriority={priority ? 'high' : undefined}
        />
      )}
    </section>
  );
};
