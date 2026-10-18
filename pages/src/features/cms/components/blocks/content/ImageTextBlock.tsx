import { SafeHtml } from "@/components/SafeHtml/SafeHtml";
import { CMS_PAGE_TITLE_CLASS } from "../headings";
import { LOCAL_IMAGE_SIZES, localImageVariant } from "../localImages";

export interface ImageTextData {
  heading?: string;
  image_url?: string;
  image_alt?: string;
  image_position?: "top" | "left" | "right";
  body_html: string;
}

const IMAGE_POSITIONS = new Set(["top", "left", "right"]);

export const ImageTextBlock = ({
  data,
  priority = false,
}: {
  data: ImageTextData;
  priority?: boolean;
}) => {
  const localImage = localImageVariant(data.image_url);
  const position = data.image_position && IMAGE_POSITIONS.has(data.image_position) ? data.image_position : "right";
  return (
    <section className="cms-image-text">
      {data.heading && <h1 className={`section-title ${CMS_PAGE_TITLE_CLASS}`}>{data.heading}</h1>}
      <div className={`capstone-content cms-image-text-content cms-image-text--${position}`}>
        {data.image_url && (
          <img
            src={localImage?.src ?? data.image_url}
            srcSet={localImage?.srcSet}
            sizes={localImage ? LOCAL_IMAGE_SIZES : undefined}
            width={localImage?.width}
            height={localImage?.height}
            alt={data.image_alt || ""}
            className="capstone-hero-image"
            loading={priority ? "eager" : "lazy"}
            decoding="async"
            fetchPriority={priority ? "high" : undefined}
          />
        )}
        <SafeHtml className="cms-prose cms-image-text-body" html={data.body_html} />
      </div>
    </section>
  );
};
