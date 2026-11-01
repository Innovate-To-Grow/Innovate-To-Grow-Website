import {useRef} from 'react';
import type {ProjectGridFilterChip, useProjectGridFilters} from '../../../hooks/useProjectGridFilters';

type FilterKey = ProjectGridFilterChip['key'];

interface ActiveFilterChipsProps {
  filters: ReturnType<typeof useProjectGridFilters>;
  /** The grid's filter change: sets the filter, then goes back to the first page. */
  changeFilter: (setter: (value: string) => void) => (value: string) => void;
  /** The ids of the Class and Industry selects, which take focus when the chip of their filter goes. */
  selectIds: Record<FilterKey, string>;
  /** No row matches: the grid's no-results state shows, with its own button that clears the filters. */
  noResults?: boolean;
}

/**
 * The Class and Industry filters in use, as chips that remove them, then "Clear Filters" once both are set (with one
 * chip it would do exactly what the chip does). While no row matches, the no-results state below offers the clear
 * instead, so the page never shows two. The search text is not a chip: its field shows it. Each button leaves with
 * the filter it clears, so focus moves first, before the filters change: to the chip that stays, or else to the
 * select of the filter just removed.
 */
export const ActiveFilterChips = ({filters, changeFilter, selectIds, noResults = false}: ActiveFilterChipsProps) => {
  const chipButtons = useRef(new Map<FilterKey, HTMLButtonElement>());
  const setterFor = (key: FilterKey) => (key === 'class' ? filters.setClassCode : filters.setIndustry);

  const remove = (key: FilterKey) => {
    const remaining = filters.filterChips.find((chip) => chip.key !== key);
    const target = remaining ? chipButtons.current.get(remaining.key) : document.getElementById(selectIds[key]);
    target?.focus();
    changeFilter(setterFor(key))('');
  };

  const clearAll = () => {
    document.getElementById(selectIds.class)?.focus();
    changeFilter(filters.setClassCode)('');
    changeFilter(filters.setIndustry)('');
  };

  return (
    <div className="project-grid-active-filters" role="group" aria-label="Active filters">
      {filters.filterChips.map((chip) => (
        <button
          key={chip.key}
          ref={(button) => {
            if (button) chipButtons.current.set(chip.key, button);
            return () => {
              chipButtons.current.delete(chip.key);
            };
          }}
          type="button"
          className="itg-btn itg-btn-outline project-grid-filter-chip"
          onClick={() => remove(chip.key)}
        >
          {/* Named by its text, not an aria-label, so page translation reaches it and the selects keep the only
              "Class" and "Industry" labels. */}
          <span>{`${chip.name}: ${chip.valueLabel}`}</span>
          <span className="sr-only">, remove filter</span>
          <span className="project-grid-filter-chip-remove" aria-hidden="true">
            ×
          </span>
        </button>
      ))}
      {filters.filterChips.length > 1 && !noResults ? (
        <button type="button" className="itg-btn itg-btn-text project-grid-clear-filters" onClick={clearAll}>
          Clear Filters
        </button>
      ) : null}
    </div>
  );
};
