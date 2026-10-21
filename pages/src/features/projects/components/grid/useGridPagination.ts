import {useMemo, useState} from 'react';
import type {ProjectGridItem} from '../projectGrid';

/** Paging over the sorted rows: rows per page (with the choices to offer) and the current page. */
export function useGridPagination(sortedRows: ProjectGridItem[], initialPageSize: number, pageSizeChoices: readonly number[]) {
  const [pageSize, setPageSizeState] = useState(() => Math.max(1, initialPageSize));
  const [page, setPage] = useState(0);

  const pageSizeOptions = useMemo(() => {
    const merged = new Set<number>([...pageSizeChoices, pageSize]);
    return Array.from(merged).sort((a, b) => a - b);
  }, [pageSize, pageSizeChoices]);

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const maxPage = totalPages - 1;
  // Persist the clamp back into `page` during render (React's "adjust state when a
  // derived value changes" pattern — a render-phase setState, not an effect, so it is
  // not a cascading-render risk). This matters when the row count shrinks under the
  // current page and then grows again (e.g. an Undo restores removed rows): without
  // writing the clamped value back, the stale out-of-range index would resurface and
  // jump the user forward. The guard makes it converge in one extra render.
  if (page > maxPage) {
    setPage(maxPage);
  }
  const currentPage = Math.min(page, maxPage);

  const pagedRows = useMemo(
    () => sortedRows.slice(currentPage * pageSize, (currentPage + 1) * pageSize),
    [currentPage, pageSize, sortedRows],
  );

  const setPageSize = (next: number) => {
    const size = Math.max(1, Math.floor(next));
    setPageSizeState(size);
    setPage(0);
  };

  /** Back to the first page at the initial size. */
  const resetPaging = () => {
    setPageSizeState(Math.max(1, initialPageSize));
    setPage(0);
  };

  return {pageSize, setPageSize, pageSizeOptions, page: currentPage, setPage, totalPages, pagedRows, resetPaging};
}
