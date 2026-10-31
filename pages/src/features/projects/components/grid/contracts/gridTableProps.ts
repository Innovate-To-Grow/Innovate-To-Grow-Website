import type {ReactNode} from 'react';
import type {
  ProjectGridColumn,
  ProjectGridColumnKey,
  ProjectGridItem,
  ProjectGridLinkScope,
  ProjectGridSortDirection,
} from './projectGrid';

export interface ProjectGridSortOption {
  field: ProjectGridColumnKey;
  label: string;
}

/** What the server's search, for text the rows do not carry, has done for the current search (useProjectGridTable). */
export interface ProjectGridServerSearch {
  /** It has not answered yet: with no rows found so far, the no-results message says more may come. */
  pending: boolean;
  /**
   * The answer that last added rows to this search, as one key of its ids; null until one has. A new key means rows
   * were sorted in among those shown and the table went back to its first page, without the visitor doing anything.
   */
  addedRowsKey: string | null;
  /** It declined the search as matching too many projects, so the abstracts were not searched: the count says so. */
  tooBroad: boolean;
  /**
   * It could not be asked (the request failed), so the abstracts were not searched either: the count says so, and a
   * search with no rows found is not taken for one with no matches.
   */
  failed: boolean;
}

export interface ProjectGridTableProps {
  columns: ProjectGridColumn[];
  rows: ProjectGridItem[];
  pagedRows: ProjectGridItem[];
  filteredCount: number;
  totalCount: number;
  /** Names the table, and its pager ("… pages"), for screen readers: "Current Projects", "Search Table 2". */
  tableLabel?: string;
  search: string;
  /** The server's search of text the rows do not carry (useProjectGridTable's `serverSearch`), when the rows have one. */
  serverSearch?: ProjectGridServerSearch;
  /** Replaces the search field (e.g. the AI search form). */
  searchControl?: ReactNode;
  controlsStatus?: ReactNode;
  searchPlaceholder?: string;
  /** Label above the search field. */
  searchLabel?: string;
  /** More fields for the filter well, after the search field (e.g. Class and Industry selects). */
  filterControls?: ReactNode;
  /**
   * The values of the extra filters in use, as their selects show them ("Engineering Capstone (CAP)"), so the
   * count and the no-results state say the filters, not only the search, narrowed the rows.
   */
  activeFilters?: string[];
  /** Shows a "Sort by" select in the results bar; Per page and View All Details move there too. */
  sortOptions?: ProjectGridSortOption[];
  sortField: ProjectGridColumnKey;
  sortDirection: ProjectGridSortDirection;
  onSearchChange: (value: string) => void;
  /** A column header was clicked: sort by it, or reverse it if it is already the sort. */
  onSortChange: (field: ProjectGridColumnKey) => void;
  /** Sort from the Sort by select, whose options name the direction ("Project title (Z to A)"). */
  onSortSelect?: (field: ProjectGridColumnKey, direction: ProjectGridSortDirection) => void;
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
  /** Loads the rows again after `error`; shown as a "Try again" button beside it. */
  onRetry?: () => void;
  /** What shows when there are no rows at all: the text under `emptyTitle`, or on its own without one. */
  emptyMessage?: string;
  /**
   * Turns the empty message into an empty state like the no-results one: this heading (at `noResultsHeadingLevel`),
   * the message, then `emptyActions`. Without it the message shows alone.
   */
  emptyTitle?: string;
  /** The empty state's action, e.g. a link to Past Projects; shown only with `emptyTitle`. */
  emptyActions?: ReactNode;
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
