export type PagerItem = number | 'gap-start' | 'gap-end';

/** Page numbers to list: the first and last pages, and a window around the current one. */
export const getPagerItems = (page: number, totalPages: number): PagerItem[] => {
  if (totalPages <= 7) {
    return Array.from({length: totalPages}, (_, index) => index);
  }
  const windowStart = page <= 2 ? 1 : page >= totalPages - 3 ? totalPages - 4 : page - 1;
  const windowEnd = page <= 2 ? 3 : page >= totalPages - 3 ? totalPages - 2 : page + 1;
  const items: PagerItem[] = [0];
  // A gap that would hide a single page shows that page instead.
  if (windowStart === 2) items.push(1);
  else if (windowStart > 2) items.push('gap-start');
  for (let index = windowStart; index <= windowEnd; index += 1) items.push(index);
  if (windowEnd === totalPages - 3) items.push(totalPages - 2);
  else if (windowEnd < totalPages - 3) items.push('gap-end');
  items.push(totalPages - 1);
  return items;
};
