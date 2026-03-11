import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  fetchPastProjects,
  type SemesterWithProjects,
  type PaginatedResponse,
} from '../../services/api/projects';
import './PastProjectsPage.css';

export const PastProjectsPage = () => {
  const [data, setData] = useState<PaginatedResponse<SemesterWithProjects> | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openSemesters, setOpenSemesters] = useState<Set<string>>(new Set());

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchPastProjects(page);
        setData(result);
        // Auto-expand the first semester on initial load
        if (result.results.length > 0 && page === 1) {
          setOpenSemesters(new Set([result.results[0].id]));
        }
      } catch {
        setError('Unable to load past projects.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [page]);

  const toggleSemester = (id: string) => {
    setOpenSemesters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  if (loading) {
    return (
      <div className="past-projects-page">
        <div className="projects-state">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="past-projects-page">
        <Link to="/current-projects" className="past-projects-back">&larr; Current Projects</Link>
        <h1 className="past-projects-title">Past Projects</h1>
        <div className="projects-state projects-error">{error}</div>
      </div>
    );
  }

  const totalPages = data ? Math.ceil(data.count / 5) : 0;

  return (
    <div className="past-projects-page">
      <Link to="/current-projects" className="past-projects-back">&larr; Current Projects</Link>
      <h1 className="past-projects-title">Past Projects</h1>

      {!data || data.results.length === 0 ? (
        <div className="projects-state">No past projects available.</div>
      ) : (
        <div className="semester-list">
          {data.results.map((semester) => {
            const isOpen = openSemesters.has(semester.id);
            return (
              <div key={semester.id} className="semester-accordion">
                <button
                  className="semester-header"
                  onClick={() => toggleSemester(semester.id)}
                  aria-expanded={isOpen}
                >
                  <span className="semester-label">{semester.label}</span>
                  <span className="semester-count">
                    {semester.projects.length} project{semester.projects.length !== 1 ? 's' : ''}
                  </span>
                  <span className={`semester-chevron ${isOpen ? 'semester-chevron-open' : ''}`}>
                    &#9654;
                  </span>
                </button>
                {isOpen && (
                  <div className="semester-body">
                    {semester.projects.length === 0 ? (
                      <p className="semester-empty">No projects in this semester.</p>
                    ) : (
                      <div className="projects-grid">
                        {semester.projects.map((project) => (
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
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="past-projects-pagination">
          <button
            className="past-projects-pagination-btn"
            disabled={!data?.previous}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </button>
          <span className="past-projects-pagination-info">
            Page {page} of {totalPages}
          </span>
          <button
            className="past-projects-pagination-btn"
            disabled={!data?.next}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};
