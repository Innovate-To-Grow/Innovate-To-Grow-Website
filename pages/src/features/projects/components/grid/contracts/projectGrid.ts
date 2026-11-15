/** The project grid's contract: its row model, links and sorting, re-exported from the modules that define them. */

export type {ProjectGridRow} from '@/features/projects/api';
export {
    getCurrentProjectDetailPath,
    getPastProjectDetailPath,
    getProjectGridRowHref,
    getProjectRowDetailPath,
    getProjectRowDetailUrl,
    hasProjectGridDetails,
    type ProjectGridLinkScope,
    type ProjectPageLinkState,
} from './projectGridLinks';
export {
    createProjectGridFingerprint,
    createProjectGridItems,
    createProjectGridRowMatcher,
    formatTermForProse,
    getDefaultClassName,
    getDisplayTeamNumber,
    getEarliestTermYear,
    getPredominantTerm,
    getProjectGridTeamCode,
    getProjectRowIds,
    PAST_PROJECT_GRID_COLUMNS,
    PROJECT_GRID_COLUMNS,
    type ProjectGridColumn,
    type ProjectGridColumnKey,
    type ProjectGridItem,
    type ProjectGridSortDirection,
    splitStudentNames,
    stripProjectGridItem,
} from './projectGridModel';
export {
    compareText,
    getProjectGridSearchValue,
    normalizeSearchText,
    sortProjectGridItems,
} from './projectGridSort';
