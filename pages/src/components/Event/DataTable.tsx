import { useState, useMemo, useEffect } from 'react';
import type { Program } from '../../services/api';
import './DataTable.css';

interface DataTableProps {
  programs: Program[];
}

interface TableRow {
  order: number;
  trackNumber: string;
  program: string;
  teamNumber: string;
  teamName: string;
  projectTitle: string;
  organization: string;
}

const flattenPresentations = (programs: Program[]): TableRow[] => {
  const rows: TableRow[] = [];
  programs.forEach(program => {
    program.tracks.forEach((track, trackIndex) => {
      track.presentations.forEach(presentation => {
        // Filter out breaks
        const isBreak = presentation.project_title?.toLowerCase().includes('break') || 
                       presentation.organization?.toLowerCase() === 'break';
        
        if (!isBreak) {
          rows.push({
            order: presentation.order,
            trackNumber: `${trackIndex + 1}`,
            program: program.program_name,
            teamNumber: presentation.team_id || '',
            teamName: presentation.team_name || '',
            projectTitle: presentation.project_title,
            organization: presentation.organization || '',
          });
        }
      });
    });
  });
  return rows.sort((a, b) => a.order - b.order);
};

export const DataTable = ({ programs }: DataTableProps) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [entriesPerPage, setEntriesPerPage] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);

  const allRows = useMemo(() => flattenPresentations(programs), [programs]);

  const filteredRows = useMemo(() => {
    if (!searchTerm.trim()) {
      return allRows;
    }
    const term = searchTerm.toLowerCase();
    return allRows.filter(row => 
      row.order.toString().includes(term) ||
      row.trackNumber.toLowerCase().includes(term) ||
      row.program.toLowerCase().includes(term) ||
      row.teamNumber.toLowerCase().includes(term) ||
      row.teamName.toLowerCase().includes(term) ||
      row.projectTitle.toLowerCase().includes(term) ||
      row.organization.toLowerCase().includes(term)
    );
  }, [allRows, searchTerm]);

  // Reset to page 1 when search term or entries per page changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, entriesPerPage]);

  // Calculate pagination
  const totalPages = Math.ceil(filteredRows.length / entriesPerPage);
  const startIndex = (currentPage - 1) * entriesPerPage;
  const endIndex = startIndex + entriesPerPage;
  const paginatedRows = filteredRows.slice(startIndex, endIndex);

  if (!programs || programs.length === 0) {
    return null;
  }

  return (
    <div className="data-table-container">
      <div className="data-table-header">
        <div className="data-table-search">
          <label htmlFor="search-input">Search:</label>
          <input
            id="search-input"
            type="text"
            className="search-input"
            placeholder="Search by any column..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="data-table-controls">
          <div className="data-table-entries">
            <label htmlFor="entries-select">Show:</label>
            <select
              id="entries-select"
              className="entries-select"
              value={entriesPerPage}
              onChange={(e) => setEntriesPerPage(Number(e.target.value))}
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
            </select>
            <span>entries</span>
          </div>
          <div className="data-table-info">
            Showing {filteredRows.length === 0 ? 0 : startIndex + 1} to {Math.min(endIndex, filteredRows.length)} of {filteredRows.length} entries
          </div>
        </div>
      </div>

      <div className="data-table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th>Order</th>
              <th>Track</th>
              <th>Program</th>
              <th>Team Number</th>
              <th>Team Name</th>
              <th>Project Title</th>
              <th>Organization</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.length === 0 ? (
              <tr>
                <td colSpan={7} className="no-results">
                  No results found
                </td>
              </tr>
            ) : (
              paginatedRows.map((row, index) => (
                <tr key={`${row.program}-${row.trackNumber}-${row.order}-${index}`}>
                  <td>{row.order}</td>
                  <td>{row.trackNumber}</td>
                  <td>{row.program}</td>
                  <td>{row.teamNumber}</td>
                  <td>{row.teamName}</td>
                  <td>{row.projectTitle}</td>
                  <td>{row.organization}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {filteredRows.length > 0 && totalPages > 1 && (
        <div className="data-table-pagination">
          <button
            className="pagination-btn"
            onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
            disabled={currentPage === 1}
          >
            Previous
          </button>
          <span className="pagination-info">
            Page {currentPage} of {totalPages}
          </span>
          <button
            className="pagination-btn"
            onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
            disabled={currentPage === totalPages}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};

