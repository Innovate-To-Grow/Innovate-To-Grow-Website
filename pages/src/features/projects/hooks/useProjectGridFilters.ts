import {useCallback, useMemo, useState} from 'react';
import {compareText, type ProjectGridItem} from '@/features/projects/components/grid/contracts/projectGrid';

export interface ProjectGridFilterOption {
  value: string;
  label: string;
}

const byLabel = (left: ProjectGridFilterOption, right: ProjectGridFilterOption) => compareText(left.label, right.label);

const distinctValues = (rows: ProjectGridItem[], pick: (row: ProjectGridItem) => string) => {
  const values = new Set<string>();
  rows.forEach((row) => {
    const value = (pick(row) ?? '').trim();
    if (value) values.add(value);
  });
  return [...values];
};

/** A filter in use, as a removable chip names it: "Class: Engineering Capstone (CAP)". */
export interface ProjectGridFilterChip {
  key: 'class' | 'industry';
  name: 'Class' | 'Industry';
  /** The chosen option's label, as its select shows it. */
  valueLabel: string;
}

/** The filters to start with, e.g. restored from the URL. */
export interface ProjectGridFilterValues {
  classCode?: string;
  industry?: string;
}

/**
 * Class and Industry filters for the current-projects table, with options built from the loaded rows.
 * Class options read "Engineering Capstone (CAP)" when the schedule names the class, else the code.
 */
export function useProjectGridFilters(
  rows: ProjectGridItem[],
  classLabels: Record<string, string> = {},
  initial: ProjectGridFilterValues = {},
) {
  const [classCode, setClassCode] = useState(initial.classCode ?? '');
  const [industry, setIndustry] = useState(initial.industry ?? '');

  const classOptions = useMemo(
    () =>
      distinctValues(rows, (row) => row.class_code)
        .map((code) => ({value: code, label: classLabels[code] ? `${classLabels[code]} (${code})` : code}))
        .sort(byLabel),
    [classLabels, rows],
  );
  const industryOptions = useMemo(
    () =>
      distinctValues(rows, (row) => row.industry)
        .map((value) => ({value, label: value}))
        .sort(byLabel),
    [rows],
  );

  // A choice that no longer exists in the rows (after a reload) stops filtering.
  const activeClass = classOptions.some((option) => option.value === classCode) ? classCode : '';
  const activeIndustry = industryOptions.some((option) => option.value === industry) ? industry : '';

  const filterRow = useMemo(
    () =>
      activeClass || activeIndustry
        ? (row: ProjectGridItem) =>
            (!activeClass || (row.class_code ?? '').trim() === activeClass) &&
            (!activeIndustry || (row.industry ?? '').trim() === activeIndustry)
        : undefined,
    [activeClass, activeIndustry],
  );

  const clear = useCallback(() => {
    setClassCode('');
    setIndustry('');
  }, []);

  // The filters in use, Class first, each with the option label its select shows.
  const filterChips = useMemo(() => {
    const chips: ProjectGridFilterChip[] = [
      {key: 'class', name: 'Class', valueLabel: classOptions.find((option) => option.value === activeClass)?.label ?? ''},
      {
        key: 'industry',
        name: 'Industry',
        valueLabel: industryOptions.find((option) => option.value === activeIndustry)?.label ?? '',
      },
    ];
    return chips.filter((chip) => chip.valueLabel);
  }, [activeClass, activeIndustry, classOptions, industryOptions]);

  // How the count line and the no-results state name the filters in use: the option labels the selects show.
  const activeLabels = useMemo(() => filterChips.map((chip) => chip.valueLabel), [filterChips]);

  return {
    classCode: activeClass,
    setClassCode,
    industry: activeIndustry,
    setIndustry,
    classOptions,
    industryOptions,
    filterRow,
    activeLabels,
    filterChips,
    clear,
  };
}
