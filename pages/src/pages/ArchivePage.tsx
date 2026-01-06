import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { fetchArchivedEvent, type EventData } from '../services/api';
import { ScheduleTable } from '../components/Event/ScheduleTable';
import { DataTable } from '../components/Event/DataTable';
import { SimpleTable } from '../components/Event/SimpleTable';
import { renderMarkdown } from '../components/Event/markdown';
import { formatEventDate } from '../utils/dateUtils';
import '../components/Event/EventPage.css';

export const ArchivePage = () => {
  const { slug } = useParams<{ slug: string }>();
  const [eventData, setEventData] = useState<EventData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadEventData = async () => {
      if (!slug) {
        setError('Invalid event slug.');
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const data = await fetchArchivedEvent(slug);
        setEventData(data);
      } catch (err) {
        setError('Unable to load archived event data.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadEventData();
  }, [slug]);

  if (loading) {
    return (
      <div className="event-container">
        <div className="event-state">Loading archived event data...</div>
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

  // Format date (using local date parsing to avoid timezone issues)
  const eventDate = formatEventDate(eventData.event_date);

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
        </div>

        {/* Top Right Section */}
        <div className="event-section event-section-top-right">
          <h2 className="event-section-title">Event Information</h2>
          <div className="event-bullets-inline">
            <ul>
              <li>This is an archived event from the past.</li>
              <li>Review schedule, projects, and teams below.</li>
              <li>You may click on a team (e.g. CSE-314) to open that team info.</li>
              <li>Then, you may click the open/close icon to view project details.</li>
            </ul>
          </div>
        </div>

        {/* Bottom Left Section */}
        <div className="event-section event-section-bottom-left">
          <h2 className="event-section-title">Event Details</h2>
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

