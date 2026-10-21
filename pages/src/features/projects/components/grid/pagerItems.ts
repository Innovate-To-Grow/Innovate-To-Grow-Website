export type PagerItem = number | 'gap-start' | 'gap-end';

/** The three pages around the current one, pinned to the start or end near either edge. */
const pagerWindow = (page: number, totalPages: number): [number, number] => {
  if (page <= 2) return [1, 3];
  if (page >= totalPages - 3) return [totalPages - 4, totalPages - 2];
  return [page - 1, page + 1];
};

/** Page numbers to list: the first and last pages, and a window around the current one. */
export const getPagerItems = (page: number, totalPages: number): PagerItem[] => {
  if (totalPages <= 7) {
    return Array.from({length: totalPages}, (_, index) => index);
  }
  const [windowStart, windowEnd] = pagerWindow(page, totalPages);
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
