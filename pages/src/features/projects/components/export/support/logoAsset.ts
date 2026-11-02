import {fetchBinaryAsset} from './binaryAsset';
import {I2G_LOGO_URL, type ExportLogoAsset} from './exportTypes';

/** Fetch the I2G logo and decode it for embedding in Excel / PDF / Word. Returns null on failure. */
export const loadI2gLogoAsset = async (url: string = I2G_LOGO_URL): Promise<ExportLogoAsset | null> => {
  const asset = await fetchBinaryAsset(url);
  if (!asset) {
    return null;
  }

  return {
    ...asset,
    dataUrl: `data:image/png;base64,${asset.base64}`,
    extension: 'png',
  };
};
