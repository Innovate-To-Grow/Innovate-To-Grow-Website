/** A same-origin file as raw bytes plus base64 (what jsPDF, ExcelJS and the .docx package take). */
export interface BinaryAsset {
  base64: string;
  bytes: Uint8Array;
}

const bytesToBase64 = (bytes: Uint8Array) => {
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.slice(index, index + chunkSize));
  }
  return btoa(binary);
};

/** Fetch a static asset for embedding in an export. Returns null on failure so the export can go on without it. */
export const fetchBinaryAsset = async (url: string): Promise<BinaryAsset | null> => {
  if (typeof fetch === 'undefined') {
    return null;
  }

  try {
    const response = await fetch(url);
    if (!response.ok) {
      return null;
    }

    const bytes = new Uint8Array(await response.arrayBuffer());
    return {base64: bytesToBase64(bytes), bytes};
  } catch {
    return null;
  }
};
