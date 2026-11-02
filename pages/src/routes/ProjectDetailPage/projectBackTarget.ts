import type {ProjectPageLinkState} from '@/features/projects/components/grid/contracts/projectGrid';

/** The lists that link to project pages, by path, with the name their back link uses. */
const LIST_NAMES: Record<string, string> = {
  '/current-projects': 'Current Projects',
  '/presenting-teams': 'Presenting Teams',
  '/past-projects': 'Past Projects',
  '/all-projects': 'All Projects',
  '/schedule': 'Event Schedule',
};

export interface ProjectBackTarget {
  href: string;
  /** "Back to Presenting Teams". */
  label: string;
  /** The list opened this page in this tab, so going back in history returns to it as the visitor left it. */
  openedFromList: boolean;
}

/**
 * Where a project page's back link goes: the list that opened it (with its search and filters), else Past
 * Projects for an archive project and Current Projects for the rest.
 */
export const resolveProjectBackTarget = (linkState: unknown, isArchiveProject: boolean): ProjectBackTarget => {
  const from = (linkState as Partial<ProjectPageLinkState> | null)?.from;
  const listName = typeof from === 'string' ? LIST_NAMES[from.split(/[?#]/)[0]] : undefined;
  if (from && listName) return {href: from, label: `Back to ${listName}`, openedFromList: true};
  return isArchiveProject
    ? {href: '/past-projects', label: 'Back to Past Projects', openedFromList: false}
    : {href: '/current-projects', label: 'Back to Current Projects', openedFromList: false};
};
