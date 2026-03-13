import {Link} from 'react-router-dom';
import {usePastProjectsData} from '../../hooks/usePastProjectsData';
import {SheetsDataTable} from '../../components/SheetsDataTable';
import type {SheetRow} from '../../services/api/sheets';
import './PastProjectsPage.css';

const PAST_COLUMNS: {key: keyof SheetRow; label: string}[] = [
  {key: 'Year-Semester', label: 'Semester'},
  {key: 'Class', label: 'Class'},
  {key: 'Team#', label: 'Team'},
  {key: 'TeamName', label: 'Team Name'},
  {key: 'Project Title', label: 'Project Title'},
  {key: 'Organization', label: 'Organization'},
  {key: 'Industry', label: 'Industry'},
];

export const PastProjectsPage = () => {
  const {rows, loading, error} = usePastProjectsData();

  return (
    <div className="past-projects-page">
      <Link to="/current-projects" className="past-projects-back">&larr; Current Projects</Link>
      <h1 className="past-projects-title">Past Projects</h1>

      <SheetsDataTable
        rows={rows}
        loading={loading}
        error={error}
        columns={PAST_COLUMNS}
      />
    </div>
  );
};
