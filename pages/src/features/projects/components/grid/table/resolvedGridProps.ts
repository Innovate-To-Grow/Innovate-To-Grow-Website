import type {AbstractsSkipped} from './projectGridResultsText';
import {useDetailsAnnouncements} from '../state/useDetailsAnnouncements';
import type {ProjectGridServerSearch, ProjectGridTableProps} from '../contracts/gridTableProps';

/** Where the table gives way to the phone list; the phone styles in projectsResponsive.css start at the same width. */
export const PHONE_LAYOUT_QUERY = '(max-width: 768px)';

const NO_ACTIVE_FILTERS: string[] = [];

export function withGridDefaults({
  searchPlaceholder = 'Search projects…',
  searchLabel = 'Search',
  noResultsHeadingLevel = 2,
  allDetailsExpanded = false,
  emptyMessage = 'No projects found.',
  countLabel = 'projects',
  toolbarPlacement = 'top',
  linkScope = 'current',
  activeFilters = NO_ACTIVE_FILTERS,
  selectable = false,
  selectedKeys = new Set<string>(),
  deleteDisabled = false,
  loadMissingDetails = false,
  ...props
}: ProjectGridTableProps) {
  return {
    ...props,
    searchPlaceholder,
    searchLabel,
    noResultsHeadingLevel,
    allDetailsExpanded,
    emptyMessage,
    countLabel,
    toolbarPlacement,
    linkScope,
    activeFilters,
    selectable,
    selectedKeys,
    deleteDisabled,
    loadMissingDetails,
  };
}

export type ResolvedGridProps = ReturnType<typeof withGridDefaults>;

export type DetailsAnnouncements = ReturnType<typeof useDetailsAnnouncements>;

/** What the table and the phone list both take to show the page's rows. */
export const rowPropsFor = (grid: ResolvedGridProps, details: DetailsAnnouncements) => ({
  columns: grid.columns,
  pagedRows: grid.pagedRows,
  linkScope: grid.linkScope,
  selectable: grid.selectable,
  selectedKeys: grid.selectedKeys,
  onToggleSelected: grid.onToggleSelected,
  expandedKeys: grid.expandedKeys,
  onToggleExpanded: details.toggleRow,
  onDeleteRow: grid.onDeleteRow,
  deleteDisabled: grid.deleteDisabled,
  loadMissingDetails: grid.loadMissingDetails,
  isRowSaved: grid.isRowSaved,
  savedRowLabel: grid.savedRowLabel,
  highlightedKeys: grid.highlightedKeys,
  announceDetails: details.announceRows,
});

/** Why the abstracts were not searched for the current search, or null when they were (or need not be). */
export const abstractsSkippedBy = (serverSearch: ProjectGridServerSearch | undefined): AbstractsSkipped | null => {
  if (serverSearch?.tooBroad) return 'too-broad';
  return serverSearch?.failed ? 'failed' : null;
};
