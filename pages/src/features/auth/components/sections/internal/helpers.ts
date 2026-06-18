/** US-only display formatter. Accepts national digits or a +1… E.164 string. */
export function formatPhoneDisplay(phoneNumber: string): string {
  let national = phoneNumber;
  if (phoneNumber.startsWith('+1')) {
    national = phoneNumber.slice(2);
  } else if (phoneNumber.startsWith('+')) {
    national = phoneNumber.slice(1);
  }

  if (national.length === 10) return `(${national.slice(0, 3)})${national.slice(3, 6)}-${national.slice(6)}`;
  if (national.length === 7) return `${national.slice(0, 3)}-${national.slice(3)}`;
  return national.replace(/(\d{3})(?=\d)/g, '$1 ').trim();
}
