import {useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode} from 'react';
import {
  type ProjectGridColumn,
  type ProjectGridColumnKey,
  type ProjectGridItem,
  type ProjectGridSortDirection,
} from './projectGrid';
import {ProjectGridDesktopTable} from './grid/ProjectGridDesktopTable';
import {ProjectGridMobileCards} from './grid/ProjectGridMobileCards';

interface ProjectGridTableProps {
  columns: ProjectGridColumn[];
  rows: ProjectGridItem[];
  pagedRows: ProjectGridItem[];
  filteredCount: number;
  totalCount: number;
  search: string;
  searchControl?: ReactNode;
  controlsStatus?: ReactNode;
  searchPlaceholder?: string;
  sortField: ProjectGridColumnKey;
  sortDirection: ProjectGridSortDirection;
  onSearchChange: (value: string) => void;
  onSortChange: (field: ProjectGridColumnKey) => void;
  expandedKeys: Set<string>;
  onToggleExpanded: (rowKey: string) => void;
  onToggleAllDetails?: () => void;
  allDetailsExpanded?: boolean;
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  pageSize: number;
  pageSizeOptions: number[];
  onPageSizeChange: (size: number) => void;
  loading?: boolean;
  error?: string | null;
  emptyMessage?: string;
  countLabel?: string;
  toolbar?: ReactNode;
  toolbarPlacement?: 'top' | 'bottom';
  selectable?: boolean;
  selectedKeys?: Set<string>;
  onToggleSelected?: (rowKey: string) => void;
  onToggleSelectAll?: () => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
}

interface PageSizeSelectProps {
  value: number;
  options: number[];
  onChange: (size: number) => void;
}

const PageSizeSelect = ({value, options, onChange}: PageSizeSelectProps) => {
  const labelId = useId();
  const buttonId = useId();
  const listboxId = useId();
  const valueId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = Math.max(0, options.indexOf(value));

  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [isOpen]);

  const focusOption = (index: number) => {
    optionRefs.current[index]?.focus();
  };

  const openListbox = (focusIndex = selectedIndex) => {
    setIsOpen(true);
    window.requestAnimationFrame(() => focusOption(focusIndex));
  };

  const chooseOption = (option: number) => {
    onChange(option);
    setIsOpen(false);
    window.requestAnimationFrame(() => buttonRef.current?.focus());
  };

  const handleButtonKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      const nextIndex = Math.min(options.length - 1, Math.max(0, selectedIndex + direction));
      openListbox(nextIndex);
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (isOpen) {
        setIsOpen(false);
      } else {
        openListbox();
      }
    }
  };

  const handleOptionKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      setIsOpen(false);
      buttonRef.current?.focus();
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      focusOption(Math.min(options.length - 1, Math.max(0, index + direction)));
    }

    if (event.key === 'Home') {
      event.preventDefault();
      focusOption(0);
    }

    if (event.key === 'End') {
      event.preventDefault();
      focusOption(options.length - 1);
    }
  };

  return (
    <div className={`project-grid-page-size${isOpen ? ' is-open' : ''}`} ref={rootRef}>
      <span id={labelId} className="project-grid-field-label">
        Per page
      </span>
      <div className="project-grid-page-size-select">
        <button
          id={buttonId}
          ref={buttonRef}
          type="button"
          className="project-grid-page-size-button"
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-controls={listboxId}
          aria-labelledby={`${labelId} ${valueId}`}
          onClick={() => (isOpen ? setIsOpen(false) : openListbox())}
          onKeyDown={handleButtonKeyDown}
        >
          <span id={valueId}>{value}</span>
          <span className="project-grid-page-size-chevron" aria-hidden="true" />
        </button>
        {isOpen ? (
          <div id={listboxId} className="project-grid-page-size-menu" role="listbox" aria-labelledby={labelId}>
            {options.map((option, index) => {
              const isSelected = option === value;

              return (
                <button
                  key={option}
                  ref={(node) => {
                    optionRefs.current[index] = node;
                  }}
                  type="button"
                  className={`project-grid-page-size-option${isSelected ? ' is-selected' : ''}`}
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => chooseOption(option)}
                  onKeyDown={(event) => handleOptionKeyDown(event, index)}
                >
                  {option}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export const ProjectGridTable = ({
  columns,
  rows,
  pagedRows,
  filteredCount,
  totalCount,
  search,
  searchControl,
  controlsStatus,
  searchPlaceholder = 'Search projects...',
  sortField,
  sortDirection,
  onSearchChange,
  onSortChange,
  expandedKeys,
  onToggleExpanded,
  onToggleAllDetails,
  allDetailsExpanded = false,
  page,
  totalPages,
  onPageChange,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
  loading,
  error,
  emptyMessage = 'No projects found.',
  countLabel = 'projects',
  toolbar,
  toolbarPlacement = 'top',
  selectable = false,
  selectedKeys = new Set<string>(),
  onToggleSelected,
  onToggleSelectAll,
  onDeleteRow,
}: ProjectGridTableProps) => {
  const searchInputId = useId();
  const toolbarElement = toolbar ? (
    <div className={`project-grid-toolbar${toolbarPlacement === 'bottom' ? ' project-grid-toolbar--bottom' : ''}`}>
      {toolbar}
    </div>
  ) : null;

  return (
    <div className="project-grid-table-shell">
      {toolbarPlacement === 'top' ? toolbarElement : null}

      <div className="project-grid-controls">
        <div className="project-grid-controls-inner">
          <div className="project-grid-controls-row">
            {searchControl ?? (
              <label className="project-grid-search-field" htmlFor={searchInputId}>
                <span className="project-grid-field-label">Search</span>
                <input
                  id={searchInputId}
                  type="search"
                  className="project-grid-search-input"
                  value={search}
                  placeholder={searchPlaceholder}
                  onChange={(event) => onSearchChange(event.target.value)}
                />
              </label>
            )}
            <div className="project-grid-controls-meta" role="group" aria-label="Results and pagination">
              <p className="project-grid-count">
                <span className="project-grid-count-value">
                  {filteredCount} of {totalCount}
                </span>{' '}
                <span className="project-grid-count-label">{countLabel}</span>
              </p>
              <PageSizeSelect value={pageSize} options={pageSizeOptions} onChange={onPageSizeChange} />
              {onToggleAllDetails ? (
                <button
                  type="button"
                  className="itg-btn itg-btn-outline project-grid-toggle-details"
                  onClick={onToggleAllDetails}
                >
                  {allDetailsExpanded ? 'Hide All Details' : 'View All Details'}
                </button>
              ) : null}
            </div>
          </div>
          {controlsStatus ? <div className="project-grid-controls-status">{controlsStatus}</div> : null}
        </div>
      </div>

      {loading ? <div className="project-grid-state">Loading project data...</div> : null}
      {error ? <div className="project-grid-state project-grid-state-error">{error}</div> : null}

      {!loading && !error ? (
        <>
          <ProjectGridDesktopTable
            columns={columns}
            rows={rows}
            pagedRows={pagedRows}
            emptyMessage={emptyMessage}
            selectable={selectable}
            selectedKeys={selectedKeys}
            onToggleSelected={onToggleSelected}
            onToggleSelectAll={onToggleSelectAll}
            sortField={sortField}
            sortDirection={sortDirection}
            onSortChange={onSortChange}
            expandedKeys={expandedKeys}
            onToggleExpanded={onToggleExpanded}
            onDeleteRow={onDeleteRow}
          />

          <ProjectGridMobileCards
            columns={columns}
            pagedRows={pagedRows}
            emptyMessage={emptyMessage}
            expandedKeys={expandedKeys}
            onToggleExpanded={onToggleExpanded}
            selectable={selectable}
            selectedKeys={selectedKeys}
            onToggleSelected={onToggleSelected}
            onDeleteRow={onDeleteRow}
          />

          {totalPages > 1 ? (
            <div className="project-grid-pagination">
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => onPageChange(page - 1)}
                disabled={page === 0}
              >
                Previous
              </button>
              <span>
                Page {page + 1} of {totalPages}
              </span>
              <button
                type="button"
                className="itg-btn itg-btn-outline"
                onClick={() => onPageChange(page + 1)}
                disabled={page >= totalPages - 1}
              >
                Next
              </button>
            </div>
          ) : null}
        </>
      ) : null}

      {toolbarPlacement === 'bottom' ? toolbarElement : null}
    </div>
  );
};
