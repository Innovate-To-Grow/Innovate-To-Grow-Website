import {useState, useCallback} from 'react';

interface ProjectImportProps {
  onImportComplete: () => void;
}

export const ProjectImport = ({onImportComplete}: ProjectImportProps) => {
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState('');

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] ?? null);
    setMessage('');
  }, []);

  const handleImport = useCallback(async () => {
    if (!file) return;
    setImporting(true);
    setMessage('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch('/api/projects/import/', {
        method: 'POST',
        headers: {Authorization: `Bearer ${localStorage.getItem('access_token')}`},
        body: formData,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Import failed (${res.status})`);
      }
      setMessage('Import successful');
      setFile(null);
      onImportComplete();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setImporting(false);
    }
  }, [file, onImportComplete]);

  return (
    <div className="project-import">
      <h3>Import Projects</h3>
      <div style={{display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap'}}>
        <input type="file" accept=".csv,.xlsx" onChange={handleFileChange} disabled={importing} />
        <button onClick={handleImport} disabled={!file || importing}>
          {importing ? 'Importing…' : 'Import'}
        </button>
      </div>
      {message && <p style={{marginTop: '0.5rem'}}>{message}</p>}
    </div>
  );
};
