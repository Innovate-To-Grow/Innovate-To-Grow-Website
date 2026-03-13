import {Link} from 'react-router-dom';
import {useCurrentProjectsData} from '../../hooks/useCurrentProjectsData';
import {SheetsDataTable} from '../../components/SheetsDataTable';
import './ProjectsPage.css';

export const ProjectsPage = () => {
  const {rows, loading, error} = useCurrentProjectsData();

  return (
    <div className="projects-page">
      <h1 className="projects-page-title">Current Projects</h1>

      <SheetsDataTable rows={rows} loading={loading} error={error} />

      <div className="projects-nav">
        <Link to="/past-projects" className="projects-nav-link">View Past Projects &rarr;</Link>
      </div>
    </div>
  );
};
