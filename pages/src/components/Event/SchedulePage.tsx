import { useState, useEffect } from 'react';
import { fetchEvent, type EventData } from '../../services/api';
import { ScheduleTable } from './ScheduleTable';
import { DataTable } from './DataTable';
import { SimpleTable } from './SimpleTable';
import './EventPage.css';

export const SchedulePage = () => {
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

