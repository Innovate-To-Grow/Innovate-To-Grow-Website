interface TableBlockData {
  heading?: string;
  columns?: unknown[];
  rows?: unknown[];
}

function stringifyCell(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }

  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function rowToCells(row: unknown, columns: string[]): string[] {
  if (Array.isArray(row)) {
    return row.map(stringifyCell);
  }

  if (row && typeof row === 'object') {
    const record = row as Record<string, unknown>;
    if (columns.length > 0) {
      return columns.map((column) => stringifyCell(record[column]));
    }
    return Object.values(record).map(stringifyCell);
  }

  return [stringifyCell(row)];
}

export const TableBlock = ({data}: {data: TableBlockData}) => {
  const columns = Array.isArray(data.columns) ? data.columns.map((column) => String(column)) : [];
  const rows = Array.isArray(data.rows) ? data.rows : [];

  return (
    <section className="cms-table-block">
      {data.heading ? <h2 className="cms-table-block-title">{data.heading}</h2> : null}
      <div className="cms-table-block-wrap">
        <table className="cms-table-block-table">
          {columns.length > 0 ? (
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
          ) : null}
          <tbody>
            {rows.map((row, rowIndex) => {
              const cells = rowToCells(row, columns);
              return (
                <tr key={rowIndex}>
                  {cells.map((cell, cellIndex) => (
                    <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
};
