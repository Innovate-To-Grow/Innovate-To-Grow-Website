import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {describe, expect, it, vi} from 'vitest';

import {TicketsSection} from '../TicketsSection';
import type {EventRegistrationSummary, Registration} from '@/features/events/api';

const registration = (overrides: Partial<Registration> = {}): Registration => ({
  id: 'registration-1',
  ticket_code: 'I2G-TEST',
  attendee_first_name: 'Ada',
  attendee_last_name: 'Lovelace',
  attendee_name: 'Ada Lovelace',
  attendee_email: 'ada@example.com',
  attendee_secondary_email: '',
  attendee_phone: '',
  phone_verified: false,
  phone_verification_required: false,
  attendee_organization: 'Acme',
  registered_at: '2026-05-01T12:00:00Z',
  ticket_email_sent_at: null,
  ticket_email_error: '',
  barcode_format: 'PDF417',
  barcode_image: 'data:image/png;base64,test',
  event: {
    id: 'event-spring',
    name: 'Spring Showcase',
    slug: 'spring-showcase',
    date: '2026-05-01',
    location: 'Campus',
    description: 'Spring event',
  },
  ticket: {id: 'ticket-spring', name: 'General Admission'},
  answers: [],
  ...overrides,
});

const openEvent = (overrides: Partial<EventRegistrationSummary> = {}): EventRegistrationSummary => ({
  id: 'event-fall',
  name: 'Fall Showcase',
  slug: 'fall-showcase',
  date: '2026-10-01',
  location: 'Conference Center',
  description: 'Fall event',
  registration: null,
  ...overrides,
});

describe('TicketsSection', () => {
  it('renders existing registrations and multiple open registration links', () => {
    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[registration()]}
          openEvents={[openEvent(), openEvent({id: 'event-winter', name: 'Winter Showcase', slug: 'winter-showcase'})]}
          ticketsLoading={false}
          liveEventLoading={false}
          resendingId={null}
          onResendTicketEmail={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText('Spring Showcase')).toBeInTheDocument();
    expect(screen.getByText('Fall Showcase')).toBeInTheDocument();
    expect(screen.getByText('Winter Showcase')).toBeInTheDocument();
    expect(screen.getAllByRole('link', {name: 'Register for this event'})[0]).toHaveAttribute(
      'href',
      '/event-registration?event=fall-showcase',
    );
  });
});
