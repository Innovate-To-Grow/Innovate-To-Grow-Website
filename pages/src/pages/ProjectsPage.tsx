import { useState, useEffect } from 'react';
import { fetchEvent, type EventData } from '../services/api';
import { DataTable } from '../components/Event/DataTable';
import './ProjectsPage.css';

export const ProjectsPage = () => {
  const [eventData, setEventData] = useState<EventData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadEventData = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchEvent();
        setEventData(data);
      } catch (err) {
        setError('Unable to load event data.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadEventData();
  }, []);

  if (loading) {
    return (
      <div className="projects-container">
        <div className="projects-state">Loading projects...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="projects-container">
        <div className="projects-state projects-error">{error}</div>
      </div>
    );
  }

  if (!eventData) {
    return null;
  }

  return (
    <div className="projects-container">
      {eventData.programs && eventData.programs.length > 0 ? (
        <DataTable programs={eventData.programs} />
      ) : (
        <div className="projects-state">No projects available.</div>
      )}
    </div>
  );
};


