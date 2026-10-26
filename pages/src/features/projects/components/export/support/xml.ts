import {toDisplayValue} from './exportTypes';

/** Drop control characters XML 1.0 forbids (keep tab/newline/CR). */
export const sanitizeXmlText = (value: string | number | null | undefined) =>
  Array.from(toDisplayValue(value))
    .filter((character) => {
      const code = character.charCodeAt(0);
      return code === 0x09 || code === 0x0a || code === 0x0d || code >= 0x20;
    })
    .join('');

export const escapeXml = (value: string | number | null | undefined) =>
  sanitizeXmlText(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
