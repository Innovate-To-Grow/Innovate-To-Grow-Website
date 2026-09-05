import { SafeHtml } from "@/components/SafeHtml/SafeHtml";

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
    src: "/assets/images/home-img-1600.webp",
    srcSet: "/assets/images/home-img-800.webp 800w, /assets/images/home-img-1600.webp 1600w",
    width: 1600,
    height: 500,
  },
  "/assets/about/engineering_capstone.webp": {
    src: "/assets/images/engineering-capstone-1280.webp",
    srcSet: "/assets/images/engineering-capstone-640.webp 640w, /assets/images/engineering-capstone-1280.webp 1280w",
    width: 1280,
    height: 854,
  },
  "/assets/about/software_engineering_capstone.webp": {
    src: "/assets/images/software-engineering-capstone-1280.webp",
    srcSet: "/assets/images/software-engineering-capstone-640.webp 640w, /assets/images/software-engineering-capstone-1280.webp 1280w",
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
