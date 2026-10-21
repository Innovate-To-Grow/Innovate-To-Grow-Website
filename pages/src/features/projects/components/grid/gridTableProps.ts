import type {ReactNode} from 'react';
import type {
  ProjectGridColumn,
  ProjectGridColumnKey,
  ProjectGridItem,
  ProjectGridLinkScope,
  ProjectGridSortDirection,
} from '../projectGrid';

export interface ProjectGridSortOption {
  field: ProjectGridColumnKey;
  label: string;
}

export interface ProjectGridTableProps {
  columns: ProjectGridColumn[];
  rows: ProjectGridItem[];
  pagedRows: ProjectGridItem[];
  filteredCount: number;
  totalCount: number;
  search: string;
  /** Replaces the search field (e.g. the AI search form). */
  searchControl?: ReactNode;
  controlsStatus?: ReactNode;
  searchPlaceholder?: string;
  /** Label above the search field. */
  searchLabel?: string;
  /** More fields for the filter well, after the search field (e.g. Class and Industry selects). */
  filterControls?: ReactNode;
  /** Shows a "Sort by" select in the results bar; Per page and View All Details move there too. */
  sortOptions?: ProjectGridSortOption[];
  sortField: ProjectGridColumnKey;
  sortDirection: ProjectGridSortDirection;
  onSearchChange: (value: string) => void;
  onSortChange: (field: ProjectGridColumnKey) => void;
  /** Clears the extra filters too when the visitor clicks "Clear search" in the no-results state. */
  onClearFilters?: () => void;
  /** Extra hint and actions for the no-results state (e.g. a link to search past projects). */
  noResultsHint?: string;
  noResultsActions?: ReactNode;
  /**
   * Level of the no-results heading, one below the heading the table sits under: 2 under a page title,
   * 3 in a card titled with an h2, 4 in a card titled with an h3.
   */
  noResultsHeadingLevel?: 2 | 3 | 4;
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
  /** Plural noun for the result count ("projects", "teams"). */
  countLabel?: string;
  /** Actions shown above the results ('top', after the filter well) or under the table ('bottom'). */
  toolbar?: ReactNode;
  toolbarPlacement?: 'top' | 'bottom';
  /** Which project page a title links to. Past-project links open in a new tab so curation work is kept. */
  linkScope?: ProjectGridLinkScope;
  selectable?: boolean;
  selectedKeys?: Set<string>;
  selectAllStateRows?: ProjectGridItem[];
  onToggleSelected?: (rowKey: string) => void;
  onToggleSelectAll?: () => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
  /** Show each row's Remove button disabled, e.g. while the rows are being turned into a shareable link. */
  deleteDisabled?: boolean;
  /** Retrieve missing details when archive rows are expanded; saved snapshots keep their own fields. */
  loadMissingDetails?: boolean;
  /** Marks rows already in the saved results with a tag after the project title. */
  isRowSaved?: (row: ProjectGridItem) => boolean;
  savedRowLabel?: string;
  /** Rows to emphasise, e.g. the ones the latest save just added. */
  highlightedKeys?: ReadonlySet<string>;
}
