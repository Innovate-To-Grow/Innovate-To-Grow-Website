import { useState, useEffect } from 'react';
import { fetchEvent, type EventData } from '../../services/api';
import { ScheduleTable } from './ScheduleTable';
import { WinnersSection } from './WinnersSection';
import { renderMarkdown } from './markdown';
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

  // Format date and time
  const eventDate = new Date(eventData.event_date).toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  const eventTime = new Date(`2000-01-01T${eventData.event_time}`).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });

  return (
    <div className="event-container">
      {/* Basic Info Section */}
      <div className="event-header">
        <h1 className="event-name">{eventData.event_name}</h1>
        <div className="event-datetime">
          <span className="event-date">{eventDate}</span>
          <span className="event-time">{eventTime}</span>
        </div>
      </div>

      {/* Upper Bullet Points */}
      {eventData.upper_bullet_points && eventData.upper_bullet_points.length > 0 && (
        <div className="event-bullets event-bullets-upper">
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

      {/* Schedule Section */}
      {eventData.programs && eventData.programs.length > 0 && (
        <ScheduleTable programs={eventData.programs} />
      )}

      {/* Lower Bullet Points */}
      {eventData.lower_bullet_points && eventData.lower_bullet_points.length > 0 && (
        <div className="event-bullets event-bullets-lower">
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

      {/* Winners Section */}
      {(eventData.track_winners.length > 0 || eventData.special_awards.length > 0) && (
        <WinnersSection
          trackWinners={eventData.track_winners}
          specialAwards={eventData.special_awards}
        />
      )}
    </div>
  );
};

