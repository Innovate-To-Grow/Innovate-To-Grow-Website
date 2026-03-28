import type {FormEvent} from 'react';
import type {EventRegistrationOptions} from '../../../features/events/api';

interface RegistrationFormStepProps {
  options: EventRegistrationOptions;
  selectedTicketId: string | null;
  answers: Record<string, string>;
  submitting: boolean;
  onTicketChange: (ticketId: string) => void;
  onAnswerChange: (questionId: string, answer: string) => void;
  onSubmit: (event: FormEvent) => void;
}

export const RegistrationFormStep = ({
  options,
  selectedTicketId,
  answers,
  submitting,
  onTicketChange,
  onAnswerChange,
  onSubmit,
}: RegistrationFormStepProps) => (
  <form onSubmit={onSubmit}>
    <div className="event-reg-form-group">
      <label className="event-reg-label">
        Select a Ticket <span className="required-mark">*</span>
      </label>
      <div className="event-reg-tickets">
        {options.tickets.map((ticket) => {
          const isSoldOut = ticket.is_sold_out;
          return (
            <label
              key={ticket.id}
              className={`event-reg-ticket-option${selectedTicketId === ticket.id ? ' selected' : ''}${isSoldOut ? ' sold-out' : ''}`}
            >
              <input
                type="radio"
                name="ticket"
                value={ticket.id}
                checked={selectedTicketId === ticket.id}
                onChange={() => onTicketChange(ticket.id)}
                disabled={isSoldOut}
              />
              <span className="event-reg-ticket-name">
                {ticket.name}
                {ticket.price !== '0.00' ? <span className="event-reg-ticket-price"> — ${ticket.price}</span> : null}
              </span>
              {ticket.remaining_quantity !== null ? (
                <span className="event-reg-ticket-meta">{isSoldOut ? 'Sold out' : `${ticket.remaining_quantity} left`}</span>
              ) : null}
            </label>
          );
        })}
      </div>
    </div>

    {options.questions
      .sort((left, right) => left.order - right.order)
      .map((question) => (
        <div key={question.id} className="event-reg-form-group">
          <label className="event-reg-label" htmlFor={`q-${question.id}`}>
            {question.text}
            {question.is_required ? <span className="required-mark">*</span> : null}
          </label>
          <textarea
            id={`q-${question.id}`}
            className="event-reg-input event-reg-textarea"
            value={answers[question.id] || ''}
            onChange={(event) => onAnswerChange(question.id, event.target.value)}
            required={question.is_required}
          />
        </div>
      ))}

    <button type="submit" className="event-reg-submit" disabled={submitting || !selectedTicketId}>
      {submitting ? <><span className="event-reg-spinner" /> Registering...</> : 'Register'}
    </button>
  </form>
);
