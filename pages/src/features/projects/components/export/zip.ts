const textEncoder = new TextEncoder();

const crcTable = Array.from({length: 256}, (_, index) => {
  let value = index;
  for (let bit = 0; bit < 8; bit += 1) {
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  }
  return value >>> 0;
});

const getCrc32 = (data: Uint8Array) => {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
};

const writeUint16 = (target: Uint8Array, offset: number, value: number) => {
  target[offset] = value & 0xff;
  target[offset + 1] = (value >>> 8) & 0xff;
};

const writeUint32 = (target: Uint8Array, offset: number, value: number) => {
  target[offset] = value & 0xff;
  target[offset + 1] = (value >>> 8) & 0xff;
  target[offset + 2] = (value >>> 16) & 0xff;
  target[offset + 3] = (value >>> 24) & 0xff;
};

const concatBytes = (parts: Uint8Array[]) => {
  const totalLength = parts.reduce((total, part) => total + part.length, 0);
  const output = new Uint8Array(totalLength);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
};

// ZIP record signatures, and "version 2.0" (the lowest that supports folders) for made-by / needed-to-extract.
const LOCAL_FILE_SIGNATURE = 0x04034b50;
const CENTRAL_DIRECTORY_SIGNATURE = 0x02014b50;
const END_OF_CENTRAL_DIRECTORY_SIGNATURE = 0x06054b50;
const ZIP_VERSION = 20;

/** Local file header: stored (no compression), no timestamp, no extra field. */
const localFileHeader = (nameBytes: Uint8Array, crc: number, size: number) => {
  const header = new Uint8Array(30 + nameBytes.length);
  writeUint32(header, 0, LOCAL_FILE_SIGNATURE);
  writeUint16(header, 4, ZIP_VERSION);
  writeUint16(header, 6, 0);
  writeUint16(header, 8, 0);
  writeUint16(header, 10, 0);
  writeUint16(header, 12, 0);
  writeUint32(header, 14, crc);
  writeUint32(header, 18, size);
  writeUint32(header, 22, size);
  writeUint16(header, 26, nameBytes.length);
  writeUint16(header, 28, 0);
  header.set(nameBytes, 30);
  return header;
};

/** Central directory entry pointing at the local header written at ``offset``. */
const centralDirectoryHeader = (nameBytes: Uint8Array, crc: number, size: number, offset: number) => {
  const header = new Uint8Array(46 + nameBytes.length);
  writeUint32(header, 0, CENTRAL_DIRECTORY_SIGNATURE);
  writeUint16(header, 4, ZIP_VERSION);
  writeUint16(header, 6, ZIP_VERSION);
  writeUint16(header, 8, 0);
  writeUint16(header, 10, 0);
  writeUint16(header, 12, 0);
  writeUint16(header, 14, 0);
  writeUint32(header, 16, crc);
  writeUint32(header, 20, size);
  writeUint32(header, 24, size);
  writeUint16(header, 28, nameBytes.length);
  writeUint16(header, 30, 0);
  writeUint16(header, 32, 0);
  writeUint16(header, 34, 0);
  writeUint16(header, 36, 0);
  writeUint32(header, 38, 0);
  writeUint32(header, 42, offset);
  header.set(nameBytes, 46);
  return header;
};

const endOfCentralDirectory = (fileCount: number, directorySize: number, directoryOffset: number) => {
  const record = new Uint8Array(22);
  writeUint32(record, 0, END_OF_CENTRAL_DIRECTORY_SIGNATURE);
  writeUint16(record, 4, 0);
  writeUint16(record, 6, 0);
  writeUint16(record, 8, fileCount);
  writeUint16(record, 10, fileCount);
  writeUint32(record, 12, directorySize);
  writeUint32(record, 16, directoryOffset);
  writeUint16(record, 20, 0);
  return record;
};

/** Build a minimal stored (uncompressed) ZIP — enough for a valid .docx OOXML package. */
export const createStoredZip = (files: Array<{name: string; content: string | Uint8Array}>) => {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  files.forEach((file) => {
    const nameBytes = textEncoder.encode(file.name);
    const contentBytes = typeof file.content === 'string' ? textEncoder.encode(file.content) : file.content;
    const crc = getCrc32(contentBytes);
    const localHeader = localFileHeader(nameBytes, crc, contentBytes.length);
    localParts.push(localHeader, contentBytes);
    centralParts.push(centralDirectoryHeader(nameBytes, crc, contentBytes.length, offset));
    offset += localHeader.length + contentBytes.length;
  });

  const centralDirectory = concatBytes(centralParts);
  return concatBytes([...localParts, centralDirectory, endOfCentralDirectory(files.length, centralDirectory.length, offset)]);
};
