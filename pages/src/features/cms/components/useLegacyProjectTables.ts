import {useEffect, type RefObject} from 'react';

const PAGE_SIZE = 10;
const MAX_PAGE_LINKS = 5;

type SortDirection = 'asc' | 'desc';

interface RowState {
  element: HTMLTableRowElement;
  cells: string[];
  detailCell: HTMLTableCellElement | null;
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

function getHiddenCellText(row: HTMLTableRowElement, className: string): string {
  return row.querySelector<HTMLTableCellElement>(`.${className}`)?.textContent?.trim() ?? '';
}

function buildDetailRow(row: RowState, colspan: number): HTMLTableRowElement {
  const detailRow = document.createElement('tr');
  detailRow.className = 'legacy-dt-child-row child';

  const detailCell = document.createElement('td');
  detailCell.colSpan = colspan;

  const detailTable = document.createElement('table');
  detailTable.className = 'legacy-project-detail-table';

  const tbody = document.createElement('tbody');
  const fields = [
    ['Abstract:', getHiddenCellText(row.element, 'legacy-dt-detail-abstract')],
    ['Student Names:', getHiddenCellText(row.element, 'legacy-dt-detail-students')],
  ].filter(([, value]) => value);

  const fallbackFields = [
    ['Project Title:', row.cells[5] ?? ''],
    ['Organization:', row.cells[6] ?? ''],
  ].filter(([, value]) => value);

  for (const [label, value] of fields.length > 0 ? fields : fallbackFields) {
    const tableRow = document.createElement('tr');
    const labelCell = document.createElement('td');
    const valueCell = document.createElement('td');
    labelCell.textContent = label;
    valueCell.textContent = value;
    tableRow.append(labelCell, valueCell);
    tbody.append(tableRow);
  }

  detailTable.append(tbody);
  detailCell.append(detailTable);
  detailRow.append(detailCell);

  return detailRow;
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
  const dataRows = Array.from(tableBody.querySelectorAll<HTMLTableRowElement>('tr')).filter((row) => (
    row !== footerRow && !row.classList.contains('legacy-dt-child-row')
  ));

  if (dataRows.length === 0) {
    return () => {};
  }

  const rows: RowState[] = dataRows.map((element) => {
    const cells = Array.from(element.cells).map((cell) => cell.textContent ?? '');
    return {
      element,
      cells,
      detailCell: element.querySelector<HTMLTableCellElement>('td.details-control'),
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

  function closeDetailRows(): void {
    tableBody.querySelectorAll<HTMLTableRowElement>('tr.legacy-dt-child-row').forEach((row) => row.remove());
    rows.forEach((row) => {
      row.element.classList.remove('shown');
      row.detailCell?.querySelector('button')?.setAttribute('aria-expanded', 'false');
      const button = row.detailCell?.querySelector<HTMLButtonElement>('button');
      if (button) {
        button.textContent = '+';
      }
    });
  }

  function toggleDetails(row: RowState): void {
    const nextRow = row.element.nextElementSibling;
    const existingDetailRow = nextRow instanceof HTMLTableRowElement && nextRow.classList.contains('legacy-dt-child-row')
      ? nextRow
      : null;
    const toggle = row.detailCell?.querySelector<HTMLButtonElement>('button') ?? null;

    if (existingDetailRow) {
      existingDetailRow.remove();
      row.element.classList.remove('shown');
      if (toggle) {
        toggle.setAttribute('aria-expanded', 'false');
        toggle.textContent = '+';
      }
      return;
    }

    row.element.insertAdjacentElement('afterend', buildDetailRow(row, headers.length || row.element.cells.length));
    row.element.classList.add('shown');
    if (toggle) {
      toggle.setAttribute('aria-expanded', 'true');
      toggle.textContent = '-';
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
    closeDetailRows();
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
    closeDetailRows();
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
  const detailListeners: Array<() => void> = [];

  rows.forEach((row) => {
    if (!row.detailCell) {
      return;
    }

    row.detailCell.textContent = '';
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'legacy-dt-detail-toggle';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Show project details');
    toggle.textContent = '+';
    row.detailCell.append(toggle);

    const handleToggle = (event: MouseEvent) => {
      event.preventDefault();
      toggleDetails(row);
    };
    row.detailCell.addEventListener('click', handleToggle);
    detailListeners.push(() => row.detailCell?.removeEventListener('click', handleToggle));
  });

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
    closeDetailRows();
    searchInput?.removeEventListener('input', handleSearch);
    detailListeners.forEach((cleanup) => cleanup());
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
