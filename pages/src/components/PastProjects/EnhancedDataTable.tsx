/**
 * Enhanced DataTable component for Past Projects.
 * Features: sorting, pagination, expandable rows, row selection, export.
 */

import { useState, useMemo, useEffect } from 'react';
import type { PastProject } from '../../services/api';
import { exportToCSV, exportToExcel, exportToPDF, printTable } from '../../utils/exportUtils';
import './EnhancedDataTable.css';

export interface EnhancedDataTableProps {
  projects: PastProject[];
  onSelectionChange?: (selectedProjects: PastProject[]) => void;
  showSelection?: boolean;
  showExport?: boolean;
  readOnly?: boolean;
}

type SortColumn = keyof PastProject | '';
type SortDirection = 'asc' | 'desc' | '';

interface SortState {
  column: SortColumn;
  direction: SortDirection;
}

export const EnhancedDataTable = ({
  projects,
  onSelectionChange,
  showSelection = false,
  showExport = true,
  readOnly = false,
}: EnhancedDataTableProps) => {
  const [entriesPerPage, setEntriesPerPage] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());
  const [sortState, setSortState] = useState<SortState>({ column: '', direction: '' });

  // Generate unique row keys
  const projectsWithKeys = useMemo(() => {
    return projects.map((project, index) => ({
      ...project,
      _rowKey: index,
    }));
  }, [projects]);

  // Handle sorting
  const sortedProjects = useMemo(() => {
    if (!sortState.column || !sortState.direction) {
      return projectsWithKeys;
    }

    const sorted = [...projectsWithKeys].sort((a, b) => {
      const aValue = a[sortState.column] || '';
      const bValue = b[sortState.column] || '';
      const comparison = String(aValue).localeCompare(String(bValue), undefined, {
        numeric: true,
        sensitivity: 'base',
      });

      return sortState.direction === 'asc' ? comparison : -comparison;
    });

    return sorted;
  }, [projectsWithKeys, sortState]);

  // Calculate pagination
  const totalPages = Math.ceil(sortedProjects.length / entriesPerPage);
  const startIndex = (currentPage - 1) * entriesPerPage;
  const endIndex = startIndex + entriesPerPage;
  const paginatedProjects = sortedProjects.slice(startIndex, endIndex);

  // Reset to page 1 when entries per page changes
  useEffect(() => {
    setCurrentPage(1);
  }, [entriesPerPage, sortState]);

  // Notify parent of selection changes
  useEffect(() => {
    if (onSelectionChange) {
      const selectedProjects = sortedProjects.filter((_, index) =>
        selectedRows.has(sortedProjects[index]._rowKey)
      );
      onSelectionChange(selectedProjects.map((p) => {
        const { _rowKey, ...project } = p;
        return project;
      }));
    }
  }, [selectedRows, sortedProjects, onSelectionChange]);

  const toggleRowExpansion = (rowKey: number) => {
    setExpandedRows((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(rowKey)) {
        newSet.delete(rowKey);
      } else {
        newSet.add(rowKey);
      }
      return newSet;
    });
  };

  const toggleRowSelection = (rowKey: number) => {
    if (!showSelection) return;
    setSelectedRows((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(rowKey)) {
        newSet.delete(rowKey);
      } else {
        newSet.add(rowKey);
      }
      return newSet;
    });
  };

  const toggleSelectAll = () => {
    if (selectedRows.size === paginatedProjects.length) {
      setSelectedRows(new Set());
    } else {
      setSelectedRows(new Set(paginatedProjects.map((p) => p._rowKey)));
    }
  };

  const handleSort = (column: keyof PastProject) => {
    setSortState((prev) => {
      if (prev.column === column) {
        // Cycle through: asc -> desc -> none
        if (prev.direction === 'asc') {
          return { column, direction: 'desc' };
        } else if (prev.direction === 'desc') {
          return { column: '', direction: '' };
        }
      }
      return { column, direction: 'asc' };
    });
  };

  const getSortIcon = (column: keyof PastProject) => {
    if (sortState.column !== column) {
      return '⇅';
    }
    return sortState.direction === 'asc' ? '↑' : '↓';
  };

  const handleExport = (format: 'csv' | 'excel' | 'pdf') => {
    const projectsToExport = sortedProjects.map((p) => {
      const { _rowKey, ...project } = p;
      return project;
    });

    switch (format) {
      case 'csv':
        exportToCSV(projectsToExport);
        break;
      case 'excel':
        exportToExcel(projectsToExport);
        break;
      case 'pdf':
        exportToPDF(projectsToExport);
        break;
    }
  };

  const handlePrint = () => {
    const projectsToPrint = sortedProjects.map((p) => {
      const { _rowKey, ...project } = p;
      return project;
    });
    printTable(projectsToPrint);
  };

  if (projects.length === 0) {
    return (
      <div className="enhanced-data-table-container">
        <div className="no-results">No projects found.</div>
      </div>
    );
  }

  const allSelected = paginatedProjects.length > 0 && paginatedProjects.every((p) => selectedRows.has(p._rowKey));
  const someSelected = paginatedProjects.some((p) => selectedRows.has(p._rowKey));

  return (
    <div className="enhanced-data-table-container">
      <div className="enhanced-data-table-header">
        <div className="enhanced-data-table-controls">
          <div className="enhanced-data-table-entries">
            <label htmlFor="entries-select">Show:</label>
            <select
              id="entries-select"
              className="entries-select"
              value={entriesPerPage}
              onChange={(e) => setEntriesPerPage(Number(e.target.value))}
              aria-label="Entries per page"
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
            <span>entries</span>
          </div>
          <div className="enhanced-data-table-info">
            Showing {sortedProjects.length === 0 ? 0 : startIndex + 1} to{' '}
            {Math.min(endIndex, sortedProjects.length)} of {sortedProjects.length} entries
          </div>
        </div>
        {showExport && (
          <div className="enhanced-data-table-export">
            <button
              type="button"
              className="export-btn"
              onClick={() => handleExport('csv')}
              aria-label="Export to CSV"
            >
              Export CSV
            </button>
            <button
              type="button"
              className="export-btn"
              onClick={() => handleExport('excel')}
              aria-label="Export to Excel"
            >
              Export Excel
            </button>
            <button
              type="button"
              className="export-btn"
              onClick={() => handleExport('pdf')}
              aria-label="Export to PDF"
            >
              Export PDF
            </button>
            <button
              type="button"
              className="export-btn"
              onClick={handlePrint}
              aria-label="Print"
            >
              Print
            </button>
          </div>
        )}
      </div>

      <div className="enhanced-data-table-wrapper">
        <table className="enhanced-data-table" role="table">
          <thead>
            <tr>
              {showSelection && (
                <th className="select-column">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={(input) => {
                      if (input) input.indeterminate = someSelected && !allSelected;
                    }}
                    onChange={toggleSelectAll}
                    aria-label="Select all rows"
                  />
                </th>
              )}
              <th>
                <button
                  type="button"
                  className="sortable-header"
                  onClick={() => handleSort('Year-Semester')}
                  aria-label="Sort by Year-Semester"
                >
                  Year-Semester {getSortIcon('Year-Semester')}
                </button>
              </th>
              <th>
                <button
                  type="button"
                  className="sortable-header"
                  onClick={() => handleSort('Class')}
                  aria-label="Sort by Class"
                >
                  Class {getSortIcon('Class')}
                </button>
              </th>
              <th>
                <button
                  type="button"
                  className="sortable-header"
                  onClick={() => handleSort('Team#')}
                  aria-label="Sort by Team Number"
                >
                  Team# {getSortIcon('Team#')}
                </button>
              </th>
              <th>
                <button
                  type="button"
                  className="sortable-header"
                  onClick={() => handleSort('Team Name')}
                  aria-label="Sort by Team Name"
                >
                  Team Name {getSortIcon('Team Name')}
                </button>
              </th>
              <th>
                <button
                  type="button"
                  className="sortable-header"
                  onClick={() => handleSort('Project Title')}
                  aria-label="Sort by Project Title"
                >
                  Project Title {getSortIcon('Project Title')}
                </button>
              </th>
              <th>
                <button
                  type="button"
                  className="sortable-header"
                  onClick={() => handleSort('Organization')}
                  aria-label="Sort by Organization"
                >
                  Organization {getSortIcon('Organization')}
                </button>
              </th>
              <th>
                <button
                  type="button"
                  className="sortable-header"
                  onClick={() => handleSort('Industry')}
                  aria-label="Sort by Industry"
                >
                  Industry {getSortIcon('Industry')}
                </button>
              </th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {paginatedProjects.map((project) => {
              const rowKey = project._rowKey;
              const isExpanded = expandedRows.has(rowKey);
              const isSelected = selectedRows.has(rowKey);
              const hasDetails = (project.Abstract && project.Abstract.trim()) || (project['Student Names'] && project['Student Names'].trim());

              return (
                <>
                  <tr
                    key={rowKey}
                    className={isSelected ? 'selected-row' : ''}
                    onClick={() => showSelection && toggleRowSelection(rowKey)}
                  >
                    {showSelection && (
                      <td className="select-column">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleRowSelection(rowKey)}
                          onClick={(e) => e.stopPropagation()}
                          aria-label={`Select row ${rowKey + 1}`}
                        />
                      </td>
                    )}
                    <td>{project['Year-Semester'] || '—'}</td>
                    <td>{project['Class'] || '—'}</td>
                    <td>{project['Team#'] || '—'}</td>
                    <td>{project['Team Name'] || '—'}</td>
                    <td>{project['Project Title'] || '—'}</td>
                    <td>{project['Organization'] || '—'}</td>
                    <td>{project['Industry'] || '—'}</td>
                    <td>
                      {hasDetails ? (
                        <button
                          type="button"
                          className="expand-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleRowExpansion(rowKey);
                          }}
                          aria-expanded={isExpanded}
                          aria-label={isExpanded ? 'Collapse details' : 'Expand details'}
                        >
                          {isExpanded ? '−' : '+'}
                        </button>
                      ) : (
                        <span className="no-details">—</span>
                      )}
                    </td>
                  </tr>
                  {isExpanded && hasDetails && (
                    <tr key={`${rowKey}-expanded`} className="expanded-row">
                      <td colSpan={showSelection ? 9 : 8} className="details-cell">
                        <div className="details-content">
                          {project.Abstract && project.Abstract.trim() && (
                            <div className="detail-section">
                              <strong>Abstract:</strong>
                              <p>{project.Abstract}</p>
                            </div>
                          )}
                          {project['Student Names'] && project['Student Names'].trim() && (
                            <div className="detail-section">
                              <strong>Student Names:</strong>
                              <p>{project['Student Names']}</p>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {sortedProjects.length > 0 && totalPages > 1 && (
        <div className="enhanced-data-table-pagination">
          <button
            type="button"
            className="pagination-btn"
            onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
            disabled={currentPage === 1}
            aria-label="Previous page"
          >
            Previous
          </button>
          <span className="pagination-info">
            Page {currentPage} of {totalPages}
          </span>
          <button
            type="button"
            className="pagination-btn"
            onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
            disabled={currentPage === totalPages}
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};


