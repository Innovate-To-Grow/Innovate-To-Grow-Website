import { useEffect, useState } from 'react';
import { fetchGoogleSheetData, type GoogleSheetDataResponse } from '../../services/api';
import './GoogleSheetTable.css';

interface GoogleSheetTableProps {
  sheetId: string;
  tableStyle?: 'default' | 'striped' | 'bordered' | 'compact';
}

export const GoogleSheetTable = ({ sheetId, tableStyle = 'default' }: GoogleSheetTableProps) => {
  const [data, setData] = useState<GoogleSheetDataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchGoogleSheetData(sheetId);
        if (cancelled) return;
        setData(response);
      } catch {
        if (cancelled) return;
        setError('Unable to load table data.');
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadData();

    return () => {
      cancelled = true;
    };
  }, [sheetId]);

  if (loading) {
    return <div className="google-sheet-table__state">Loading table...</div>;
  }

  if (error) {
    return <div className="google-sheet-table__state google-sheet-table__state--error">{error}</div>;
  }

  const headers = data?.headers ?? [];
  const rows = data?.rows ?? [];

  if (headers.length === 0 && rows.length === 0) {
    return <div className="google-sheet-table__state">No data available.</div>;
  }

  return (
    <div className={`google-sheet-table google-sheet-table--${tableStyle}`}>
      <div className="google-sheet-table__scroll">
        <table className="google-sheet-table__table">
          {headers.length > 0 && (
            <thead>
              <tr>
                {headers.map((header, index) => (
                  <th key={`header-${index}`}>{header}</th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`cell-${rowIndex}-${cellIndex}`}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
