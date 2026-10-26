import {I2G_LOGO_URL, type ExportLogoAsset} from './exportTypes';

const bytesToBase64 = (bytes: Uint8Array) => {
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.slice(index, index + chunkSize));
  }
  return btoa(binary);
};

/** Fetch the I2G logo and decode it for embedding in Excel / PDF / Word. Returns null on failure. */
export const loadI2gLogoAsset = async (): Promise<ExportLogoAsset | null> => {
  if (typeof fetch === 'undefined') {
    return null;
  }

  try {
    const response = await fetch(I2G_LOGO_URL);
    if (!response.ok) {
      return null;
    }

    const bytes = new Uint8Array(await response.arrayBuffer());
    const base64 = bytesToBase64(bytes);
    return {
      base64,
      bytes,
      dataUrl: `data:image/png;base64,${base64}`,
      extension: 'png',
    };
  } catch {
    return null;
  }
};
