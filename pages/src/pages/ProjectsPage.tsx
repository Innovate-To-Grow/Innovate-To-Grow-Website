import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchCurrentProjects, type SemesterWithProjects } from '../services/api/projects';
import './ProjectsPage.css';

export const ProjectsPage = () => {
  const [data, setData] = useState<SemesterWithProjects | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchCurrentProjects();
        setData(result);
      } catch {
        setError('Unable to load current projects.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className="projects-page">
        <div className="projects-state">Loading...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="projects-page">
        <h1 className="projects-page-title">Current Projects</h1>
        <div className="projects-state projects-error">
          {error || 'No published projects available.'}
        </div>
        <div className="projects-nav">
          <Link to="/past-projects" className="projects-nav-link">View Past Projects</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="projects-page">
      <h1 className="projects-page-title">Current Projects</h1>
      <p className="projects-page-subtitle">{data.label}</p>

      {data.projects.length === 0 ? (
        <div className="projects-state">No projects in this semester yet.</div>
      ) : (
        <div className="projects-grid">
          {data.projects.map((project) => (
            <Link
              key={project.id}
              to={`/projects/${project.id}`}
              className="project-card"
            >
              <div className="project-card-body">
                <h2 className="project-card-title">{project.project_title}</h2>
                {project.team_name && (
                  <p className="project-card-team">{project.team_name}</p>
                )}
                {project.organization && (
                  <p className="project-card-org">{project.organization}</p>
                )}
                {project.industry && (
                  <span className="project-card-industry">{project.industry}</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}

      <div className="projects-nav">
        <Link to="/past-projects" className="projects-nav-link">View Past Projects &rarr;</Link>
      </div>
    </div>
  );
};
