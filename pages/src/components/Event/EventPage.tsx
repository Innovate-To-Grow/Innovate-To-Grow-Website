import { useState, useEffect } from 'react';
import { fetchEvent, type EventData } from '../../services/api';
import { ScheduleTable } from './tables/ScheduleTable';
import { DataTable } from './tables/DataTable';
import { SimpleTable } from './tables/SimpleTable';
import { renderMarkdown } from './utils/markdown';
import './EventPage.css';

export const EventPage = () => {
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
      <div className="event-container">
        <div className="event-state">Loading event data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="event-container">
        <div className="event-state event-error">{error}</div>
      </div>
    );
  }

  if (!eventData) {
    return null;
  }

  // Format date
  const eventDate = new Date(eventData.event_date).toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  return (
    <div className="event-container">
      {/* Main Event Title */}
      <h1 className="event-main-title">{eventData.event_name}: {eventDate}</h1>

      {/* Top Section - 2x2 Grid */}
      <div className="event-top-section">
        {/* Top Left Section */}
        <div className="event-section event-section-top-left">
          <h2 className="event-section-title">
            {eventData.event_name}: {eventDate}
          </h2>
          {eventData.upper_bullet_points && eventData.upper_bullet_points.length > 0 && (
            <div className="event-bullets-inline">
              <ul>
                {eventData.upper_bullet_points.map((bullet, index) => (
                  <li
                    key={`upper-${index}`}
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(bullet) }}
                  />
                ))}
              </ul>
            </div>
          )}
          <button className="btn-register-now">REGISTER NOW!</button>
        </div>

        {/* Top Right Section */}
        <div className="event-section event-section-top-right">
          <h2 className="event-section-title">Preparing for the Event</h2>
          <div className="event-bullets-inline">
            <ul>
              <li>Register ASAP to attend in person (no zoom this edition)</li>
              <li>Review schedule, projects, and teams (below): check for updates!</li>
              <li>You may click on a team (e.g. CSE-314) to open that team info.</li>
              <li>Then, you may click the open/close icon to view project details.</li>
            </ul>
          </div>
          <div className="event-buttons-group">
            <button className="btn-for-attendees">FOR ATTENDEES</button>
            <button className="btn-for-judges">FOR JUDGES</button>
          </div>
        </div>

        {/* Bottom Left Section */}
        <div className="event-section event-section-bottom-left">
          <h2 className="event-section-title">Attend in Person: (EVENT MAP)</h2>
          {eventData.lower_bullet_points && eventData.lower_bullet_points.length > 0 && (
            <div className="event-bullets-inline">
              <ul>
                {eventData.lower_bullet_points.map((bullet, index) => (
                  <li
                    key={`lower-${index}`}
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(bullet) }}
                  />
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Bottom Right Section - Map Placeholder */}
        <div className="event-section event-section-bottom-right">
          <div className="map-placeholder">
            {/* Map image will go here */}
          </div>
        </div>
      </div>

      {/* Expo Table Section */}
      {eventData.expo_table && eventData.expo_table.length > 0 && (
        <SimpleTable title="EXPO: POSTERS AND DEMOS" rows={eventData.expo_table} />
      )}

      {/* Schedule Section */}
      {eventData.programs && eventData.programs.length > 0 && (
        <ScheduleTable programs={eventData.programs} />
      )}

      {/* Reception Table Section */}
      {eventData.reception_table && eventData.reception_table.length > 0 && (
        <SimpleTable title="AWARDS & RECEPTION" rows={eventData.reception_table} />
      )}

      {/* Data Table Section */}
      {eventData.programs && eventData.programs.length > 0 && (
        <DataTable programs={eventData.programs} />
      )}
    </div>
  );
};


