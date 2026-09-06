import type {ImgHTMLAttributes} from 'react';

const BRAND_IMAGES = {
    i2g: {
        src: '/assets/images/i2glogo-512.webp',
        srcSet: '/assets/images/i2glogo-256.webp 256w, /assets/images/i2glogo-512.webp 512w',
        width: 512,
        height: 512,
        alt: 'Innovate To Grow',
    },
    fullname: {
        src: '/assets/images/i2g-fullname-960.webp',
        srcSet: '/assets/images/i2g-fullname-480.webp 480w, /assets/images/i2g-fullname-960.webp 960w',
        width: 960,
        height: 345,
        alt: 'Innovate To Grow',
    },
    ucm: {
        src: '/assets/images/ucmlogo-230.webp',
        srcSet: '/assets/images/ucmlogo-115.webp 115w, /assets/images/ucmlogo-230.webp 230w',
        width: 230,
        height: 57,
        alt: 'UC Merced',
    },
} as const;

interface ResponsiveBrandImageProps
    extends Omit<ImgHTMLAttributes<HTMLImageElement>, 'src' | 'srcSet' | 'width' | 'height'> {
    brand: keyof typeof BRAND_IMAGES;
}

export const ResponsiveBrandImage = ({brand, alt, sizes = '100vw', ...props}: ResponsiveBrandImageProps) => {
    const image = BRAND_IMAGES[brand];
    return (
        <picture>
            <source type="image/webp" srcSet={image.srcSet} sizes={sizes}/>
            <img
                {...props}
                src={image.src}
                srcSet={image.srcSet}
                sizes={sizes}
                width={image.width}
                height={image.height}
                alt={alt ?? image.alt}
                decoding="async"
            />
        </picture>
    );
};
