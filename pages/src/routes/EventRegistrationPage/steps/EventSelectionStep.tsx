import type {EventRegistrationSummary} from '@/features/events/api';
import {formatEventDate} from './helpers';

interface EventSelectionStepProps {
  events: EventRegistrationSummary[];
  selectedEventSlug: string;
  onSelect: (eventSlug: string) => void;
}

export const EventSelectionStep = ({events, selectedEventSlug, onSelect}: EventSelectionStepProps) => {
  if (events.length === 0) {
    return <div className="event-reg-loading">No event is currently accepting registrations.</div>;
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
                <span className={`event-reg-event-status${registered ? ' is-registered' : ''}`}>
                  {registered ? 'Registered' : 'Open'}
                </span>
              </div>
              <dl className="event-reg-event-meta">
                <div>
                  <dt>Date</dt>
                  <dd>{formatEventDate(event.date)}</dd>
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
              className="event-reg-submit event-reg-event-action"
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
