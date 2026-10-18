import {useCallback, useMemo, useState} from 'react';
import type {ProjectGridItem} from '@/features/projects/components/projectGrid';

export interface ProjectGridFilterOption {
  value: string;
  label: string;
}

const byLabel = (left: ProjectGridFilterOption, right: ProjectGridFilterOption) =>
  left.label.localeCompare(right.label, undefined, {numeric: true, sensitivity: 'base'});

const distinctValues = (rows: ProjectGridItem[], pick: (row: ProjectGridItem) => string) => {
  const values = new Set<string>();
  rows.forEach((row) => {
    const value = (pick(row) ?? '').trim();
    if (value) values.add(value);
  });
  return [...values];
};

/**
 * Class and Industry filters for the current-projects table, with options built from the loaded rows.
 * Class options read "Engineering Capstone (CAP)" when the schedule names the class, else the code.
 */
export function useProjectGridFilters(rows: ProjectGridItem[], classLabels: Record<string, string> = {}) {
  const [classCode, setClassCode] = useState('');
  const [industry, setIndustry] = useState('');

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

  return {
    classCode: activeClass,
    setClassCode,
    industry: activeIndustry,
    setIndustry,
    classOptions,
    industryOptions,
    filterRow,
    clear,
  };
}
