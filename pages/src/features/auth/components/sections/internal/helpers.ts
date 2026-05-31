export function getDialCode(regionCode: string): string {
  return `+${regionCode.split('-')[0]}`;
}

export function formatPhoneDisplay(phoneNumber: string, region: string): string {
  const countryCode = region.split('-')[0];
  const prefix = `+${countryCode}`;

  let national = phoneNumber;
  if (phoneNumber.startsWith(prefix)) {
    national = phoneNumber.slice(prefix.length);
  } else if (phoneNumber.startsWith('+')) {
    national = phoneNumber.slice(1);
    if (national.startsWith(countryCode)) {
      national = national.slice(countryCode.length);
    }
  }

  if (countryCode === '1') {
    if (national.length === 10) return `(${national.slice(0, 3)})${national.slice(3, 6)}-${national.slice(6)}`;
    if (national.length === 7) return `${national.slice(0, 3)}-${national.slice(3)}`;
    return national.replace(/(\d{3})(?=\d)/g, '$1 ').trim();
  }
  if (countryCode === '86' && national.length === 11) return `${national.slice(0, 3)} ${national.slice(3, 7)} ${national.slice(7)}`;
  if ((countryCode === '852' || countryCode === '853') && national.length === 8) return `${national.slice(0, 4)} ${national.slice(4)}`;
  if (countryCode === '886' && national.length === 9) return `${national.slice(0, 1)} ${national.slice(1, 5)} ${national.slice(5)}`;
  if ((countryCode === '81' || countryCode === '82') && national.length === 10) return `${national.slice(0, 2)} ${national.slice(2, 6)} ${national.slice(6)}`;
  if (countryCode === '44' && national.length === 10) return `${national.slice(0, 4)} ${national.slice(4)}`;
  if (countryCode === '91' && national.length === 10) return `${national.slice(0, 5)} ${national.slice(5)}`;
  if (countryCode === '61' && national.length === 9) return `${national.slice(0, 3)} ${national.slice(3, 6)} ${national.slice(6)}`;
  if (countryCode === '49' && (national.length === 10 || national.length === 11)) return `${national.slice(0, 4)} ${national.slice(4)}`;
  if (countryCode === '33' && national.length === 9) return `${national.slice(0, 1)} ${national.slice(1, 3)} ${national.slice(3, 5)} ${national.slice(5, 7)} ${national.slice(7)}`;
  if (countryCode === '55' && national.length === 11) return `${national.slice(0, 2)} ${national.slice(2, 7)}-${national.slice(7)}`;
  if (countryCode === '52' && national.length === 10) return `${national.slice(0, 2)} ${national.slice(2, 6)} ${national.slice(6)}`;

  const groups: string[] = [];
  for (let index = 0; index < national.length; index += 4) {
    groups.push(national.slice(index, index + 4));
  }
  return groups.join(' ');
}
