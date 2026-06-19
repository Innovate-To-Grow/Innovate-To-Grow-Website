import {useDeferredValue, useEffect, useMemo, useState} from 'react';
import {
  createProjectGridFingerprint,
  getProjectGridSearchValue,
  hasProjectGridDetails,
  sortProjectGridItems,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridSortDirection,
} from './projectGrid';

/** Default choices for the “rows per page” control (hook merges in the current size if needed). */
export const PROJECT_GRID_PAGE_SIZE_OPTIONS = [5, 10, 25, 50, 100] as const;

interface UseProjectGridTableOptions {
  rows: ProjectGridItem[];
  /** Initial rows per page; user can change this via the table control. */
  pageSize?: number;
  /** Allowed page sizes in the dropdown; current size is always included. */
  pageSizeOptions?: readonly number[];
  defaultSortField: ProjectGridColumnKey;
  defaultSortDirection?: ProjectGridSortDirection;
  initialSearch?: string;
  /** Seed every expandable row open on mount (used by the shared, read-only view). */
  expandAllByDefault?: boolean;
}

export function useProjectGridTable({
  rows,
  pageSize: initialPageSize = 10,
  pageSizeOptions: pageSizeChoices = PROJECT_GRID_PAGE_SIZE_OPTIONS,
  defaultSortField,
  defaultSortDirection = 'asc',
  initialSearch = '',
  expandAllByDefault = false,
}: UseProjectGridTableOptions) {
  const [pageSize, setPageSizeState] = useState(() => Math.max(1, initialPageSize));
  const [search, setSearch] = useState(initialSearch);
  const deferredSearch = useDeferredValue(search);
  const [sortField, setSortField] = useState<ProjectGridColumnKey>(defaultSortField);
  const [sortDirection, setSortDirection] = useState<ProjectGridSortDirection>(defaultSortDirection);
  const [page, setPage] = useState(0);

  const pageSizeOptions = useMemo(() => {
    const merged = new Set<number>([...pageSizeChoices, pageSize]);
    return Array.from(merged).sort((a, b) => a - b);
  }, [pageSize, pageSizeChoices]);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    // Reset the user's in-progress search when the seed prop changes (it tracks the
    // ?value= URL param / external team search, which can change while mounted).
    // `search` holds intervening user input, so this is a genuine prop-change reset,
    // not a derivable value. Doing it during render with a previous-prop ref would
    // shift the update from after-paint to render-phase — an observable timing change
    // we must not introduce — so the effect-phase sync stays.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- external prop-change reset; render-phase alternative would change effect timing
    setSearch(initialSearch);
  }, [initialSearch]);

  const filteredRows = useMemo(() => {
    if (!deferredSearch.trim()) {
      return rows;
    }
    const query = deferredSearch.trim().toLowerCase();
    return rows.filter((row) => getProjectGridSearchValue(row).includes(query));
  }, [deferredSearch, rows]);

  const sortedRows = useMemo(
    () => sortProjectGridItems(filteredRows, sortField, sortDirection),
    [filteredRows, sortDirection, sortField],
  );

  // Rows the user has explicitly checked (independent of the current search
  // filter), in the table's natural order. Drives "merge only what I selected".
  const selectedRows = useMemo(
    () => rows.filter((row) => selectedKeys.has(row.__key)),
    [rows, selectedKeys],
  );

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

  const expandableKeys = useMemo(
    () => rows.filter((row) => hasProjectGridDetails(row)).map((row) => row.__key),
    [rows],
  );

  const allDetailsExpanded =
    expandableKeys.length > 0 && expandableKeys.every((rowKey) => expandedKeys.has(rowKey));

  useEffect(() => {
    if (!expandAllByDefault) {
      return;
    }
    // Seed every expandable row open. Adding an already-present key is a no-op, so a
    // user can still collapse rows afterward without this re-expanding them. The
    // functional updater merges into prior expand state derived from rows/props, so it
    // cannot be replaced by a render-time derivation without dropping user toggles.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- merges seed-open keys into existing expand state; not derivable in render without losing user toggles
    setExpandedKeys((current) => {
      const next = new Set(current);
      expandableKeys.forEach((rowKey) => next.add(rowKey));
      return next;
    });
  }, [expandAllByDefault, expandableKeys]);

  useEffect(() => {
    const rowKeys = new Set(rows.map((row) => row.__key));

    // Prune expanded/selected keys for rows that no longer exist when `rows` changes,
    // while keeping the rest of the user's expand/selection state. Both updaters read
    // prior state, so this stale-key cleanup is genuine React-to-prop sync, not a value
    // derivable in render.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- prunes stale keys against current rows; preserves remaining user expand state
    setExpandedKeys((current) => {
      const next = new Set<string>();
      current.forEach((rowKey) => {
        if (rowKeys.has(rowKey)) {
          next.add(rowKey);
        }
      });
      return next;
    });

    setSelectedKeys((current) => {
      const next = new Set<string>();
      current.forEach((rowKey) => {
        if (rowKeys.has(rowKey)) {
          next.add(rowKey);
        }
      });
      return next;
    });
  }, [rows]);

  const toggleSort = (field: ProjectGridColumnKey) => {
    if (field === sortField) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
    setPage(0);
  };

  const toggleExpanded = (rowKey: string) => {
    setExpandedKeys((current) => {
      const next = new Set(current);
      if (next.has(rowKey)) {
        next.delete(rowKey);
      } else {
        next.add(rowKey);
      }
      return next;
    });
  };

  const toggleSelected = (rowKey: string) => {
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(rowKey)) {
        next.delete(rowKey);
      } else {
        next.add(rowKey);
      }
      return next;
    });
  };

  const clearSelection = () => {
    setSelectedKeys(new Set());
  };

  const selectAllRows = () => {
    setSelectedKeys(new Set(rows.map((row) => row.__key)));
  };

  // Replace the selection with exactly the given rows. Used for a filter-aware "select all" that
  // must not reach rows hidden by the active search (so a later bulk delete can't remove unseen rows).
  const selectRows = (rowsToSelect: ProjectGridItem[]) => {
    setSelectedKeys(new Set(rowsToSelect.map((row) => row.__key)));
  };

  const toggleAllDetails = () => {
    if (allDetailsExpanded) {
      setExpandedKeys(new Set());
      return;
    }
    setExpandedKeys(new Set(expandableKeys));
  };

  const removeSelectedRows = (sourceRows: ProjectGridItem[]) =>
    sourceRows.filter((row) => !selectedKeys.has(row.__key));

  const keepSelectedRows = (sourceRows: ProjectGridItem[]) =>
    sourceRows.filter((row) => selectedKeys.has(row.__key));

  const fingerprints = useMemo(
    () => new Set(rows.map((row) => createProjectGridFingerprint(row))),
    [rows],
  );

  return {
    search,
    setSearch,
    sortField,
    sortDirection,
    toggleSort,
    pageSize,
    setPageSize,
    pageSizeOptions,
    page: currentPage,
    setPage,
    totalPages,
    filteredRows,
    sortedRows,
    selectedRows,
    pagedRows,
    expandedKeys,
    toggleExpanded,
    selectedKeys,
    toggleSelected,
    clearSelection,
    selectAllRows,
    selectRows,
    toggleAllDetails,
    allDetailsExpanded,
    hasSelection: selectedKeys.size > 0,
    removeSelectedRows,
    keepSelectedRows,
    fingerprints,
  };
}
