export const formatSemesterLabel = (raw: string): string =>
  raw.replace(/^(\d{4})-[12]\s+/, '$1 ');
