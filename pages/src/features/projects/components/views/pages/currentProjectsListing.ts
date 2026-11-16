import {type ProjectGridSortOption} from '../../grid/table/ProjectGridTable';
import {formatTermForProse, getPredominantTerm, type ProjectGridRow} from '../../grid/contracts/projectGrid';
import {pluralize} from '../../shared/utils/saveResults';

export const CURRENT_SORT_OPTIONS: ProjectGridSortOption[] = [
  {field: 'class_code', label: 'Team number'},
  {field: 'project_title', label: 'Project title'},
  {field: 'organization', label: 'Organization'},
];

/** The line under the title: the term, the count, and how many teams present. */
export const metaLine = (rows: ProjectGridRow[], countLabel: 'projects' | 'teams') => {
  const term = formatTermForProse(getPredominantTerm(rows));
  const presentingCount = rows.filter((row) => row.is_presenting === 'Yes').length;
  const meta =
    countLabel === 'teams'
      ? [term, `${pluralize(rows.length, 'team')} presenting`]
      : [
          term,
          pluralize(rows.length, 'project'),
          presentingCount ? `${pluralize(presentingCount, 'team')} presenting at the showcase` : '',
        ];
  return meta.filter(Boolean).join(' · ');
};
