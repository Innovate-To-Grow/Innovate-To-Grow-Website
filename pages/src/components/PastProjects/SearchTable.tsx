/**
 * SearchTable component for Past Projects.
 * Features: multiple filter controls, real-time filtering, row selection.
 */

import { useState, useMemo, useEffect, useCallback } from 'react';
import type { PastProject } from '../../services/api';
import { EnhancedDataTable } from './EnhancedDataTable';
import './SearchTable.css';

export interface SearchTableProps {
  allProjects: PastProject[];
  tableId: string;
  onKeepSelected?: (projects: PastProject[]) => void;
  onDeleteSelected?: (projects: PastProject[]) => void;
  onDeleteTable?: () => void;
  readOnly?: boolean;
}

interface FilterState {
  yearSemester: string;
  class: string[];
  teamNumber: string;
  teamName: string;
  projectTitle: string;
  organization: string;
  industry: string;
  studentNames: string;
}

export const SearchTable = ({
  allProjects,
  tableId,
  onKeepSelected,
  onDeleteSelected,
  onDeleteTable,
  readOnly = false,
}: SearchTableProps) => {
  const [filters, setFilters] = useState<FilterState>({
    yearSemester: '',
    class: [],
    teamNumber: '',
    teamName: '',
    projectTitle: '',
    organization: '',
    industry: '',
    studentNames: '',
  });

  const [selectedProjects, setSelectedProjects] = useState<PastProject[]>([]);
  const [showFilters, setShowFilters] = useState(true);

  // Get unique values for dropdowns
  const uniqueValues = useMemo(() => {
    const years = new Set<string>();
    const classes = new Set<string>();
    const industries = new Set<string>();

    allProjects.forEach((project) => {
      if (project['Year-Semester']) years.add(project['Year-Semester']);
      if (project['Class']) classes.add(project['Class']);
      if (project['Industry']) industries.add(project['Industry']);
    });

    return {
      years: Array.from(years).sort().reverse(),
      classes: Array.from(classes).sort(),
      industries: Array.from(industries).sort(),
    };
  }, [allProjects]);

  // Apply filters
  const filteredProjects = useMemo(() => {
    return allProjects.filter((project) => {
      // Year-Semester filter
      if (filters.yearSemester && project['Year-Semester'] !== filters.yearSemester) {
        return false;
      }

      // Class filter (multi-select)
      if (filters.class.length > 0 && !filters.class.includes(project['Class'] || '')) {
        return false;
      }

      // Team# filter (supports ranges like "1-5" or exact match)
      if (filters.teamNumber) {
        const teamNum = project['Team#'] || '';
        if (filters.teamNumber.includes('-')) {
          const [start, end] = filters.teamNumber.split('-').map((n) => parseInt(n.trim(), 10));
          const projectNum = parseInt(teamNum, 10);
          if (isNaN(projectNum) || projectNum < start || projectNum > end) {
            return false;
          }
        } else {
          if (!teamNum.toLowerCase().includes(filters.teamNumber.toLowerCase())) {
            return false;
          }
        }
      }

      // Team Name filter (case-insensitive text search)
      if (filters.teamName && !(project['Team Name'] || '').toLowerCase().includes(filters.teamName.toLowerCase())) {
        return false;
      }

      // Project Title filter (case-insensitive text search)
      if (filters.projectTitle && !(project['Project Title'] || '').toLowerCase().includes(filters.projectTitle.toLowerCase())) {
        return false;
      }

      // Organization filter (case-insensitive text search)
      if (filters.organization && !(project['Organization'] || '').toLowerCase().includes(filters.organization.toLowerCase())) {
        return false;
      }

      // Industry filter
      if (filters.industry && project['Industry'] !== filters.industry) {
        return false;
      }

      // Student Names filter (case-insensitive text search)
      if (filters.studentNames && !(project['Student Names'] || '').toLowerCase().includes(filters.studentNames.toLowerCase())) {
        return false;
      }

      return true;
    });
  }, [allProjects, filters]);

  const handleFilterChange = useCallback((field: keyof FilterState, value: string | string[]) => {
    setFilters((prev) => ({
      ...prev,
      [field]: value,
    }));
  }, []);

  const handleClassToggle = useCallback((className: string) => {
    setFilters((prev) => ({
      ...prev,
      class: prev.class.includes(className)
        ? prev.class.filter((c) => c !== className)
        : [...prev.class, className],
    }));
  }, []);

  const clearAllFilters = useCallback(() => {
    setFilters({
      yearSemester: '',
      class: [],
      teamNumber: '',
      teamName: '',
      projectTitle: '',
      organization: '',
      industry: '',
      studentNames: '',
    });
  }, []);

  const handleKeepSelected = useCallback(() => {
    if (onKeepSelected && selectedProjects.length > 0) {
      onKeepSelected(selectedProjects);
    }
  }, [onKeepSelected, selectedProjects]);

  const handleDeleteSelected = useCallback(() => {
    if (onDeleteSelected && selectedProjects.length > 0) {
      onDeleteSelected(selectedProjects);
      setSelectedProjects([]);
    }
  }, [onDeleteSelected, selectedProjects]);

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.yearSemester) count++;
    if (filters.class.length > 0) count++;
    if (filters.teamNumber) count++;
    if (filters.teamName) count++;
    if (filters.projectTitle) count++;
    if (filters.organization) count++;
    if (filters.industry) count++;
    if (filters.studentNames) count++;
    return count;
  }, [filters]);

  return (
    <div className="search-table-container" id={tableId}>
      <div className="search-table-header">
        <h3 className="search-table-title">Search Table {tableId}</h3>
        <div className="search-table-actions">
          {!readOnly && (
            <>
              <button
                type="button"
                className="action-btn keep-btn"
                onClick={handleKeepSelected}
                disabled={selectedProjects.length === 0}
                aria-label="Keep selected rows"
              >
                Keep Selected Rows ({selectedProjects.length})
              </button>
              <button
                type="button"
                className="action-btn delete-btn"
                onClick={handleDeleteSelected}
                disabled={selectedProjects.length === 0}
                aria-label="Delete selected rows"
              >
                Delete Selected Rows ({selectedProjects.length})
              </button>
            </>
          )}
          {onDeleteTable && (
            <button
              type="button"
              className="action-btn remove-btn"
              onClick={onDeleteTable}
              aria-label="Delete this search table"
            >
              Delete Table
            </button>
          )}
        </div>
      </div>

      <div className="search-table-filters-section">
        <div className="filters-header">
          <button
            type="button"
            className="toggle-filters-btn"
            onClick={() => setShowFilters(!showFilters)}
            aria-expanded={showFilters}
            aria-label={showFilters ? 'Hide filters' : 'Show filters'}
          >
            {showFilters ? '−' : '+'} Filters
            {activeFilterCount > 0 && <span className="filter-count">({activeFilterCount})</span>}
          </button>
          {activeFilterCount > 0 && (
            <button
              type="button"
              className="clear-filters-btn"
              onClick={clearAllFilters}
              aria-label="Clear all filters"
            >
              Clear All Filters
            </button>
          )}
        </div>

        {showFilters && (
          <div className="filters-grid">
            <div className="filter-group">
              <label htmlFor={`year-semester-${tableId}`}>Year-Semester:</label>
              <select
                id={`year-semester-${tableId}`}
                value={filters.yearSemester}
                onChange={(e) => handleFilterChange('yearSemester', e.target.value)}
                aria-label="Filter by Year-Semester"
              >
                <option value="">All</option>
                {uniqueValues.years.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label>Class:</label>
              <div className="multi-select-container">
                {uniqueValues.classes.map((className) => (
                  <label key={className} className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={filters.class.includes(className)}
                      onChange={() => handleClassToggle(className)}
                      aria-label={`Filter by ${className}`}
                    />
                    <span>{className}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="filter-group">
              <label htmlFor={`team-number-${tableId}`}>Team#:</label>
              <input
                id={`team-number-${tableId}`}
                type="text"
                value={filters.teamNumber}
                onChange={(e) => handleFilterChange('teamNumber', e.target.value)}
                placeholder="e.g., 1 or 1-5"
                aria-label="Filter by Team Number"
              />
            </div>

            <div className="filter-group">
              <label htmlFor={`team-name-${tableId}`}>Team Name:</label>
              <input
                id={`team-name-${tableId}`}
                type="text"
                value={filters.teamName}
                onChange={(e) => handleFilterChange('teamName', e.target.value)}
                placeholder="Search team names..."
                aria-label="Filter by Team Name"
              />
            </div>

            <div className="filter-group">
              <label htmlFor={`project-title-${tableId}`}>Project Title:</label>
              <input
                id={`project-title-${tableId}`}
                type="text"
                value={filters.projectTitle}
                onChange={(e) => handleFilterChange('projectTitle', e.target.value)}
                placeholder="Search project titles..."
                aria-label="Filter by Project Title"
              />
            </div>

            <div className="filter-group">
              <label htmlFor={`organization-${tableId}`}>Organization:</label>
              <input
                id={`organization-${tableId}`}
                type="text"
                value={filters.organization}
                onChange={(e) => handleFilterChange('organization', e.target.value)}
                placeholder="Search organizations..."
                aria-label="Filter by Organization"
              />
            </div>

            <div className="filter-group">
              <label htmlFor={`industry-${tableId}`}>Industry:</label>
              <select
                id={`industry-${tableId}`}
                value={filters.industry}
                onChange={(e) => handleFilterChange('industry', e.target.value)}
                aria-label="Filter by Industry"
              >
                <option value="">All</option>
                {uniqueValues.industries.map((industry) => (
                  <option key={industry} value={industry}>
                    {industry}
                  </option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label htmlFor={`student-names-${tableId}`}>Student Names:</label>
              <input
                id={`student-names-${tableId}`}
                type="text"
                value={filters.studentNames}
                onChange={(e) => handleFilterChange('studentNames', e.target.value)}
                placeholder="Search student names..."
                aria-label="Filter by Student Names"
              />
            </div>
          </div>
        )}
      </div>

      <div className="search-table-results">
        <EnhancedDataTable
          projects={filteredProjects}
          onSelectionChange={setSelectedProjects}
          showSelection={!readOnly}
          showExport={true}
          readOnly={readOnly}
        />
      </div>
    </div>
  );
};


