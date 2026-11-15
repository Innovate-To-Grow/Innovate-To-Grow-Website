import {useProjectGridFilters, type ProjectGridFilterOption} from '../../../hooks/list/useProjectGridFilters';

interface FilterSelectProps {
  /** The select's id: the filter chips focus it when its chip goes (ActiveFilterChips). */
  id: string;
  label: string;
  allLabel: string;
  value: string;
  options: ProjectGridFilterOption[];
  onChange: (value: string) => void;
}

const FilterSelect = ({id, label, allLabel, value, options, onChange}: FilterSelectProps) => (
  <div className="itg-field project-grid-filter">
    <label className="project-grid-field-label" htmlFor={id}>
      {label}
    </label>
    <select
      id={id}
      className="itg-select project-grid-select"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{allLabel}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  </div>
);

interface CurrentProjectsFiltersProps {
  filters: ReturnType<typeof useProjectGridFilters>;
  changeFilter: (setter: (value: string) => void) => (value: string) => void;
  selectIds: {class: string; industry: string};
}

/** The Class and Industry selects. */
export const CurrentProjectsFilters = ({filters, changeFilter, selectIds}: CurrentProjectsFiltersProps) => (
  <>
    <FilterSelect
      id={selectIds.class}
      label="Class"
      allLabel="All classes"
      value={filters.classCode}
      options={filters.classOptions}
      onChange={changeFilter(filters.setClassCode)}
    />
    <FilterSelect
      id={selectIds.industry}
      label="Industry"
      allLabel="All industries"
      value={filters.industry}
      options={filters.industryOptions}
      onChange={changeFilter(filters.setIndustry)}
    />
  </>
);
