import {useEffect, type RefObject} from 'react';

const PAGE_SIZE = 10;
const MAX_PAGE_LINKS = 5;

type SortDirection = 'asc' | 'desc';

interface RowState {
  element: HTMLTableRowElement;
  cells: string[];
  searchableText: string;
}

function normalizeText(value: string): string {
  return value.replace(/\s+/g, ' ').trim().toLocaleLowerCase();
}

function compareCellValues(a: string, b: string, direction: SortDirection): number {
  const result = a.localeCompare(b, undefined, {
    numeric: true,
    sensitivity: 'base',
  });
  return direction === 'asc' ? result : -result;
}

function createPaginationButton(
  label: string,
  classNames: string[],
  disabled: boolean,
  onClick: () => void,
): HTMLAnchorElement {
  const button = document.createElement('a');
  button.className = classNames.join(' ');
  button.textContent = label;
  button.setAttribute('aria-controls', 'example');

  button.addEventListener('click', (event) => {
    event.preventDefault();
    if (!disabled) {
      onClick();
    }
  });

  return button;
}

function enhanceProjectTable(table: HTMLTableElement): () => void {
  const tbody = table.tBodies.item(0);
  const wrapper = table.closest<HTMLElement>('.dataTables_wrapper');
  const pagination = wrapper?.querySelector<HTMLElement>('.dataTables_paginate') ?? null;
  const info = wrapper?.querySelector<HTMLElement>('.dataTables_info') ?? null;
  const footerRow = tbody?.querySelector<HTMLTableRowElement>('tr.legacy-dt-footer-row') ?? null;

  if (!tbody || !wrapper || !pagination || !info) {
    return () => {};
  }

  const tableBody = tbody;
  const paginationEl = pagination;
  const infoEl = info;
  const headers = Array.from(table.tHead?.querySelectorAll<HTMLTableCellElement>('th') ?? []);
  const dataRows = Array.from(tableBody.querySelectorAll<HTMLTableRowElement>('tr')).filter(
    (row) => row !== footerRow,
  );

  if (dataRows.length === 0) {
    return () => {};
  }

  const rows: RowState[] = dataRows.map((element) => {
    const cells = Array.from(element.cells).map((cell) => cell.textContent ?? '');
    return {
      element,
      cells,
      searchableText: normalizeText(cells.join(' ')),
    };
  });

  const initialSortIndex = headers.findIndex(
    (header) => header.classList.contains('sorting_asc') || header.classList.contains('sorting_desc'),
  );
  let sortColumn = initialSortIndex >= 0 ? initialSortIndex : 1;
  let sortDirection: SortDirection = headers[sortColumn]?.classList.contains('sorting_asc') ? 'asc' : 'desc';
  let orderedRows = [...rows];
  let currentPage = 1;

  const placeholder = wrapper.querySelector<HTMLElement>('.dataTables_filter .legacy-dt-search-input');
  let searchInput = wrapper.querySelector<HTMLInputElement>('.dataTables_filter input.legacy-dt-search-input');
  if (!searchInput) {
    searchInput = document.createElement('input');
    searchInput.type = 'search';
    searchInput.className = 'legacy-dt-search-input';
    searchInput.setAttribute('aria-controls', table.id || 'example');
    searchInput.autocomplete = 'off';
    if (placeholder) {
      placeholder.replaceWith(searchInput);
    } else {
      wrapper.querySelector('.dataTables_filter label')?.append(searchInput);
    }
  }

  function updateSortClasses(): void {
    headers.forEach((header, index) => {
      if (header.classList.contains('sorting_disabled')) {
        header.removeAttribute('aria-sort');
        return;
      }

      header.classList.remove('sorting_asc', 'sorting_desc');
      header.classList.add('sorting');
      if (index === sortColumn) {
        header.classList.add(sortDirection === 'asc' ? 'sorting_asc' : 'sorting_desc');
        header.setAttribute('aria-sort', sortDirection === 'asc' ? 'ascending' : 'descending');
      } else {
        header.removeAttribute('aria-sort');
      }
    });

    rows.forEach((row) => {
      Array.from(row.element.cells).forEach((cell, index) => {
        cell.classList.toggle('sorting_1', index === sortColumn);
      });
    });
  }

  function applySort(): void {
    orderedRows = [...rows].sort((a, b) =>
      compareCellValues(a.cells[sortColumn] ?? '', b.cells[sortColumn] ?? '', sortDirection),
    );

    const fragment = document.createDocumentFragment();
    orderedRows.forEach((row) => fragment.append(row.element));
    tableBody.insertBefore(fragment, footerRow);
    if (footerRow) {
      tableBody.append(footerRow);
    }
  }

  function renderPagination(pageCount: number): void {
    paginationEl.textContent = '';

    paginationEl.append(
      createPaginationButton('Previous', ['paginate_button', 'previous', ...(currentPage === 1 ? ['disabled'] : [])], currentPage === 1, () => {
        currentPage = Math.max(1, currentPage - 1);
        render();
      }),
    );

    const pageLinks = document.createElement('span');
    let firstPage = Math.max(1, currentPage - Math.floor(MAX_PAGE_LINKS / 2));
    const lastPage = Math.min(pageCount, firstPage + MAX_PAGE_LINKS - 1);
    firstPage = Math.max(1, lastPage - MAX_PAGE_LINKS + 1);

    for (let page = firstPage; page <= lastPage; page += 1) {
      pageLinks.append(
        createPaginationButton(
          String(page),
          ['paginate_button', ...(page === currentPage ? ['current'] : [])],
          false,
          () => {
            currentPage = page;
            render();
          },
        ),
      );
    }

    paginationEl.append(pageLinks);
    paginationEl.append(
      createPaginationButton('Next', ['paginate_button', 'next', ...(currentPage === pageCount ? ['disabled'] : [])], currentPage === pageCount, () => {
        currentPage = Math.min(pageCount, currentPage + 1);
        render();
      }),
    );
  }

  function render(): void {
    const query = normalizeText(searchInput?.value ?? '');
    const matchingRows = orderedRows.filter((row) => !query || row.searchableText.includes(query));
    const pageCount = Math.max(1, Math.ceil(matchingRows.length / PAGE_SIZE));
    currentPage = Math.min(currentPage, pageCount);

    const startIndex = (currentPage - 1) * PAGE_SIZE;
    const visibleRows = matchingRows.slice(startIndex, startIndex + PAGE_SIZE);
    const visibleElements = new Set(visibleRows.map((row) => row.element));

    rows.forEach((row) => {
      row.element.classList.toggle('is-hidden', !visibleElements.has(row.element));
      row.element.classList.remove('odd', 'even');
    });

    visibleRows.forEach((row, index) => {
      row.element.classList.add(index % 2 === 0 ? 'odd' : 'even');
    });

    const showingStart = matchingRows.length === 0 ? 0 : startIndex + 1;
    const showingEnd = Math.min(startIndex + PAGE_SIZE, matchingRows.length);
    infoEl.textContent =
      matchingRows.length === rows.length
        ? `Showing ${showingStart} to ${showingEnd} of ${rows.length} entries`
        : `Showing ${showingStart} to ${showingEnd} of ${matchingRows.length} entries (filtered from ${rows.length} total entries)`;

    renderPagination(pageCount);
  }

  const handleSearch = () => {
    currentPage = 1;
    render();
  };
  searchInput.addEventListener('input', handleSearch);

  const headerListeners: Array<() => void> = [];
  headers.forEach((header, index) => {
    if (header.classList.contains('sorting_disabled')) {
      return;
    }

    header.tabIndex = 0;
    header.style.cursor = 'pointer';
    const handleSort = () => {
      if (sortColumn === index) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
      } else {
        sortColumn = index;
        sortDirection = 'asc';
      }
      currentPage = 1;
      updateSortClasses();
      applySort();
      render();
    };
    const handleKeyboardSort = (event: KeyboardEvent) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        handleSort();
      }
    };

    header.addEventListener('click', handleSort);
    header.addEventListener('keydown', handleKeyboardSort);
    headerListeners.push(() => {
      header.removeEventListener('click', handleSort);
      header.removeEventListener('keydown', handleKeyboardSort);
    });
  });

  updateSortClasses();
  applySort();
  render();

  return () => {
    searchInput?.removeEventListener('input', handleSearch);
    headerListeners.forEach((cleanup) => cleanup());
  };
}

export function useLegacyProjectTables(
  containerRef: RefObject<HTMLElement | null>,
  dependencyKey: unknown,
): void {
  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    let cleanupTables: Array<() => void> = [];
    const frameId = window.requestAnimationFrame(() => {
      const tables = Array.from(container.querySelectorAll<HTMLTableElement>('table.legacy-projects-table'));
      cleanupTables = tables.map((table) => enhanceProjectTable(table));
    });

    return () => {
      window.cancelAnimationFrame(frameId);
      cleanupTables.forEach((cleanup) => cleanup());
    };
  }, [containerRef, dependencyKey]);
}
