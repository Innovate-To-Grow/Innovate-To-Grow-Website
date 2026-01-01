import type { ExpoRow, ReceptionRow } from '../../services/api';
import './SimpleTable.css';

interface SimpleTableProps {
  title: string;
  rows: ExpoRow[] | ReceptionRow[];
}

// Format time to display "9:00 AM" or "9:00 PM" format (always includes AM/PM)
const formatTime = (timeStr: string): string => {
  if (!timeStr) return '';
  
  // If it's already in format with AM/PM, normalize it
  const hasAmPm = /\s*(AM|PM|am|pm)/i.test(timeStr);
  if (hasAmPm) {
    // Normalize to uppercase AM/PM
    return timeStr.trim().replace(/\s*(am|pm)/i, (match) => ` ${match.toUpperCase()}`);
  }
  
  // If it's a date string, parse and format with AM/PM
  try {
    const date = new Date(timeStr);
    if (!isNaN(date.getTime())) {
      const hours = date.getHours();
      const minutes = date.getMinutes();
      const ampm = hours >= 12 ? 'PM' : 'AM';
      const hours12 = hours % 12 || 12;
      return `${hours12}:${minutes.toString().padStart(2, '0')} ${ampm}`;
    }
  } catch (e) {
    // If parsing fails, try to extract time pattern from string and add AM/PM
    const timeMatch = timeStr.match(/(\d{1,2}):(\d{2})/);
    if (timeMatch) {
      const hour = parseInt(timeMatch[1], 10);
      const minute = parseInt(timeMatch[2], 10);
      const ampm = hour >= 12 ? 'PM' : 'AM';
      const hour12 = hour % 12 || 12;
      return `${hour12}:${minute.toString().padStart(2, '0')} ${ampm}`;
    }
  }
  
  // If we can't parse it, try to add AM/PM to existing format
  const timeMatch = timeStr.match(/(\d{1,2}):(\d{2})/);
  if (timeMatch) {
    const hour = parseInt(timeMatch[1], 10);
    const minute = parseInt(timeMatch[2], 10);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const hour12 = hour % 12 || 12;
    return `${hour12}:${minute.toString().padStart(2, '0')} ${ampm}`;
  }
  
  return timeStr;
};

export const SimpleTable = ({ title, rows }: SimpleTableProps) => {
  if (!rows || rows.length === 0) {
    return null;
  }

  // Find header row and extract room, filter out header rows from data
  let room = '';
  const dataRows = rows.filter((row) => {
    if (row.time === 'Room:') {
      room = row.description || '';
      return false; // Exclude header row
    }
    return true; // Include data rows
  });

  // If no room found in header, try to get from first row's room field
  if (!room && rows[0]?.room) {
    room = rows[0].room;
  }

  if (dataRows.length === 0) {
    return null;
  }

  return (
    <div className="simple-table-container">
      <h2 className="simple-table-title">{title}</h2>
      <table className="simple-table">
        <thead>
          <tr className="simple-table-header-row">
            <th className="simple-table-room-header">Room:</th>
            <th className="simple-table-room-value">{room}</th>
          </tr>
        </thead>
        <tbody>
          {dataRows.map((row, index) => (
            <tr key={index} className="simple-table-row">
              <td className="simple-table-time-cell">{formatTime(row.time)}</td>
              <td className="simple-table-description-cell">{row.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

