import type {ImgHTMLAttributes} from 'react';

import i2gFullname480 from '@/assets/images/i2g-fullname-480.webp';
import i2gFullname960 from '@/assets/images/i2g-fullname-960.webp';
import i2gLogo256 from '@/assets/images/i2glogo-256.webp';
import i2gLogo512 from '@/assets/images/i2glogo-512.webp';
import ucmLogo115 from '@/assets/images/ucmlogo-115.webp';
import ucmLogo230 from '@/assets/images/ucmlogo-230.webp';

const BRAND_IMAGES = {
    i2g: {
        src: i2gLogo512,
        srcSet: `${i2gLogo256} 256w, ${i2gLogo512} 512w`,
        width: 512,
        height: 512,
        alt: 'Innovate To Grow',
    },
    fullname: {
        src: i2gFullname960,
        srcSet: `${i2gFullname480} 480w, ${i2gFullname960} 960w`,
        width: 960,
        height: 345,
        alt: 'Innovate To Grow',
    },
    ucm: {
        src: ucmLogo230,
        srcSet: `${ucmLogo115} 115w, ${ucmLogo230} 230w`,
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
