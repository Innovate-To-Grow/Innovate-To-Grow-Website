import {useCurrentProjectsData} from '../../hooks/useCurrentProjectsData';
import {SheetsDataTable} from '../../components/SheetsDataTable';
import './ProjectsTeamsPage.css';

export const ProjectsTeamsPage = () => {
  const {rows, loading, error} = useCurrentProjectsData();

  return (
    <div className="projects-teams-page">
      <h1 className="projects-teams-page-title">Projects &amp; Teams</h1>

      <p className="projects-teams-page-text">
        Browse all student teams and their projects for the current Innovate to Grow semester.
        Use the search bar to filter by team number, team name, project title, organization,
        industry, or class. Click on a row to expand and view the project abstract and student
        names.
      </p>

      <section className="projects-teams-page-section">
        <SheetsDataTable rows={rows} loading={loading} error={error} />
      </section>
    </div>
  );
};
