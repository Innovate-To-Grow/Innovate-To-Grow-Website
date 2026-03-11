import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { fetchProjectDetail, type ProjectDetail } from '../../services/api/projects';
import './ProjectDetailPage.css';

export const ProjectDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [id]);

  useEffect(() => {
    if (!id) return;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchProjectDetail(id);
        setProject(data);
      } catch {
        setError('Unable to load this project.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  if (loading) {
    return (
      <div className="project-detail">
        <div className="projects-state">Loading...</div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="project-detail">
        <Link to="/current-projects" className="project-detail-back">&larr; Back to Projects</Link>
        <div className="projects-state projects-error">{error || 'Project not found.'}</div>
      </div>
    );
  }

  return (
    <div className="project-detail">
      <Link to="/current-projects" className="project-detail-back">&larr; Back to Projects</Link>

      <h1 className="project-detail-title">{project.project_title}</h1>

      <div className="project-detail-meta">
        {project.semester_label && (
          <div className="project-detail-meta-item">
            <span className="project-detail-meta-label">Semester</span>
            <span className="project-detail-meta-value">{project.semester_label}</span>
          </div>
        )}
        {project.team_name && (
          <div className="project-detail-meta-item">
            <span className="project-detail-meta-label">Team</span>
            <span className="project-detail-meta-value">{project.team_name}</span>
          </div>
        )}
        {project.team_number && (
          <div className="project-detail-meta-item">
            <span className="project-detail-meta-label">Team #</span>
            <span className="project-detail-meta-value">{project.team_number}</span>
          </div>
        )}
        {project.organization && (
          <div className="project-detail-meta-item">
            <span className="project-detail-meta-label">Organization</span>
            <span className="project-detail-meta-value">{project.organization}</span>
          </div>
        )}
        {project.industry && (
          <div className="project-detail-meta-item">
            <span className="project-detail-meta-label">Industry</span>
            <span className="project-detail-meta-value">{project.industry}</span>
          </div>
        )}
        {project.class_code && (
          <div className="project-detail-meta-item">
            <span className="project-detail-meta-label">Class</span>
            <span className="project-detail-meta-value">{project.class_code}</span>
          </div>
        )}
      </div>

      {project.abstract && (
        <div className="project-detail-section">
          <h2 className="project-detail-section-title">Abstract</h2>
          <p className="project-detail-abstract">{project.abstract}</p>
        </div>
      )}

      {project.student_names && (
        <div className="project-detail-section">
          <h2 className="project-detail-section-title">Team Members</h2>
          <p className="project-detail-students">{project.student_names}</p>
        </div>
      )}
    </div>
  );
};
