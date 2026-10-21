import type {FormSectionProps} from './types';

/** The ticket choice and the event's questions. */
export const RegistrationDetailsFields = ({form, errors, showError, errorClass}: FormSectionProps) => (
  <>
    <div className={`event-reg-form-group${errorClass(errors.missingTicket)}`}>
      <label className="itg-label event-reg-label">
        Select a Ticket <span className="required-mark">*</span>
      </label>
      <div className="event-reg-tickets">
        {form.options.tickets.map((ticket) => (
            <label
              key={ticket.id}
              className={`event-reg-ticket-option${form.selectedTicketId === ticket.id ? ' selected' : ''}`}
            >
              <input
                type="radio"
                name="ticket"
                value={ticket.id}
                checked={form.selectedTicketId === ticket.id}
                onChange={() => form.onTicketChange(ticket.id)}
              />
              <span className="event-reg-ticket-name">{ticket.name}</span>
            </label>
          ))}
      </div>
      {showError && errors.missingTicket ? (
        <p className="event-reg-field-error">Please select a ticket.</p>
      ) : null}
    </div>

    {form.options.questions
      .sort((left, right) => left.order - right.order)
      .map((question) => {
        const qMissing = errors.missingAnswerIds.has(question.id);
        return (
        <div key={question.id} className={`event-reg-form-group${errorClass(qMissing)}`}>
          <label className="itg-label event-reg-label" htmlFor={`q-${question.id}`}>
            {question.text}
            {question.is_required ? <span className="required-mark">*</span> : null}
          </label>
          <textarea
            id={`q-${question.id}`}
            className="itg-input event-reg-input event-reg-textarea"
            value={form.answers[question.id] || ''}
            onChange={(event) => form.onAnswerChange(question.id, event.target.value)}
          />
          {showError && qMissing ? (
            <p className="event-reg-field-error">This field is required.</p>
          ) : null}
        </div>
        );
      })}
  </>
);
