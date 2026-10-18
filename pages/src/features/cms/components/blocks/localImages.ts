/**
 * Responsive variants for images that ship with the SPA.
 *
 * CMS blocks store the original asset path (for example
 * `/assets/about/engineering_capstone.webp`). When the path is one of the known
 * bundled images, the block serves the pre-sized WebP variants with a srcset
 * and intrinsic dimensions instead, so the browser can reserve the space and
 * pick the right size. Any other URL is used as-is.
 */

export interface LocalImageVariant {
  src: string;
  srcSet: string;
  width: number;
  height: number;
}

const LOCAL_IMAGES: Record<string, LocalImageVariant> = {
  '/assets/images/home_img.jpg': {
    src: '/assets/images/home-img-1600.webp',
    srcSet: '/assets/images/home-img-800.webp 800w, /assets/images/home-img-1600.webp 1600w',
    width: 1600,
    height: 500,
  },
  '/assets/about/engineering_capstone.webp': {
    src: '/assets/images/engineering-capstone-1280.webp',
    srcSet: '/assets/images/engineering-capstone-640.webp 640w, /assets/images/engineering-capstone-1280.webp 1280w',
    width: 1280,
    height: 854,
  },
  '/assets/about/software_engineering_capstone.webp': {
    src: '/assets/images/software-engineering-capstone-1280.webp',
    srcSet: '/assets/images/software-engineering-capstone-640.webp 640w, /assets/images/software-engineering-capstone-1280.webp 1280w',
    width: 1280,
    height: 854,
  },
};

/** `sizes` that goes with a local variant's srcset. */
export const LOCAL_IMAGE_SIZES = '(max-width: 768px) 100vw, 1280px';

export function localImageVariant(url: string | undefined): LocalImageVariant | undefined {
  return url ? LOCAL_IMAGES[url] : undefined;
}
