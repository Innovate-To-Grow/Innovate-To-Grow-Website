import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchPastEventsList, type PastEventListItem } from '../services/api';
import { formatEventDateShort } from '../utils/dateUtils';
import './PastEventsPage.css';

export const PastEventsPage = () => {
  const [pastEvents, setPastEvents] = useState<PastEventListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadPastEvents = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchPastEventsList();
        setPastEvents(data);
      } catch (err) {
        setError('Unable to load past events.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadPastEvents();
  }, []);

  if (loading) {
    return (
      <div className="past-events-container">
        <div className="past-events-state">Loading past events...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="past-events-container">
        <div className="past-events-state past-events-error">{error}</div>
      </div>
    );
  }

  return (
    <div className="past-events-container">
      <h1 className="past-events-title">Past Events Archive</h1>
      
      {pastEvents.length === 0 ? (
        <div className="past-events-empty">
          <p>No past events found.</p>
        </div>
      ) : (
        <ul className="past-events-list">
          {pastEvents.map((event) => {
            // Format date (using local date parsing to avoid timezone issues)
            const eventDate = formatEventDateShort(event.event_date);
            
            return (
              <li key={event.slug} className="past-events-item">
                <Link to={`/archive/${event.slug}`} className="past-events-link">
                  <span className="past-events-name">{event.event_name}</span>
                  <span className="past-events-date">{eventDate}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

