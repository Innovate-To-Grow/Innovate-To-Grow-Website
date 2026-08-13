import { SafeHtml } from "@/components/SafeHtml/SafeHtml";
import engineering640 from "@/assets/images/engineering-capstone-640.webp";
import engineering1280 from "@/assets/images/engineering-capstone-1280.webp";
import home800 from "@/assets/images/home-img-800.webp";
import home1600 from "@/assets/images/home-img-1600.webp";
import software640 from "@/assets/images/software-engineering-capstone-640.webp";
import software1280 from "@/assets/images/software-engineering-capstone-1280.webp";

export interface ImageTextData {
  heading?: string;
  image_url?: string;
  image_alt?: string;
  image_position?: "top" | "left" | "right";
  body_html: string;
}

const LOCAL_IMAGES: Record<
  string,
  { src: string; srcSet: string; width: number; height: number }
> = {
  "/assets/images/home_img.jpg": {
    src: home1600,
    srcSet: `${home800} 800w, ${home1600} 1600w`,
    width: 1600,
    height: 500,
  },
  "/assets/about/engineering_capstone.webp": {
    src: engineering1280,
    srcSet: `${engineering640} 640w, ${engineering1280} 1280w`,
    width: 1280,
    height: 854,
  },
  "/assets/about/software_engineering_capstone.webp": {
    src: software1280,
    srcSet: `${software640} 640w, ${software1280} 1280w`,
    width: 1280,
    height: 854,
  },
};

export const ImageTextBlock = ({
  data,
  priority = false,
}: {
  data: ImageTextData;
  priority?: boolean;
}) => {
  const localImage = data.image_url ? LOCAL_IMAGES[data.image_url] : undefined;
  return (
    <section className="cms-image-text">
      {data.heading && <h1 className="section-title">{data.heading}</h1>}
      <div className="capstone-content">
        {data.image_url && (
          <img
            src={localImage?.src ?? data.image_url}
            srcSet={localImage?.srcSet}
            sizes={localImage ? "(max-width: 768px) 100vw, 1280px" : undefined}
            width={localImage?.width}
            height={localImage?.height}
            alt={data.image_alt || ""}
            className="capstone-hero-image"
            loading={priority ? "eager" : "lazy"}
            decoding="async"
            fetchPriority={priority ? "high" : undefined}
          />
        )}
        <SafeHtml html={data.body_html} />
      </div>
    </section>
  );
};
