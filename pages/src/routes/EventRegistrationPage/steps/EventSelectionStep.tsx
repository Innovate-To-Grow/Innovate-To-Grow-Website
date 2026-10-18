import type {EventRegistrationSummary} from '@/features/events/api';
import {formatEventDateRange} from '@/features/events/formatEventDateRange';
import './eventSelection.css';

interface EventSelectionStepProps {
  events: EventRegistrationSummary[];
  selectedEventSlug: string;
  onSelect: (eventSlug: string) => void;
}

export const EventSelectionStep = ({events, selectedEventSlug, onSelect}: EventSelectionStepProps) => {
  if (events.length === 0) {
    return <p className="event-reg-loading">No event is currently accepting registrations.</p>;
  }

  return (
    <section className="event-reg-event-list" aria-label="Open events">
      {events.map((event) => {
        const registered = Boolean(event.registration);
        const isSelected = selectedEventSlug === event.slug;
        return (
          <article
            key={event.id}
            className={`event-reg-event-card${registered ? ' is-registered' : ''}${isSelected ? ' is-selected' : ''}`}
          >
            <div className="event-reg-event-card-main">
              <div className="event-reg-event-card-header">
                <h2 className="event-reg-event-card-title">{event.name}</h2>
                <span className={`itg-tag event-reg-event-status ${registered ? 'itg-tag-saved is-registered' : 'itg-tag-new'}`}>
                  {registered ? 'Registered' : 'Open'}
                </span>
              </div>
              <dl className="event-reg-event-meta">
                <div>
                  <dt>Date</dt>
                  <dd>{formatEventDateRange(event.date, event.end_date)}</dd>
                </div>
                <div>
                  <dt>Location</dt>
                  <dd>{event.location || 'TBA'}</dd>
                </div>
              </dl>
              {event.description ? <p className="event-reg-event-description">{event.description}</p> : null}
            </div>
            <button
              type="button"
              className={`itg-btn ${registered ? 'itg-btn-outline' : 'itg-btn-primary'} event-reg-event-action`}
              onClick={() => onSelect(event.slug)}
            >
              {registered ? 'View Ticket' : 'Register'}
            </button>
          </article>
        );
      })}
    </section>
  );
};
