import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import type {Registration} from '@/features/events/api';
import {resendTicketEmail} from '@/features/events/api';
import {DoneState} from '@/routes/EventRegistrationPage/steps/DoneState';
import {LoadingState} from '@/routes/EventRegistrationPage/steps/LoadingState';
import {formatEventDate, getRegistrationErrorMessage} from '@/routes/EventRegistrationPage/steps/helpers';

vi.mock('@/features/events/api', () => ({
  resendTicketEmail: vi.fn(),
}));

const registration: Registration = {
  id: 'registration-1',
  ticket_code: 'I2G-123',
  attendee_first_name: 'Ada',
  attendee_last_name: 'Lovelace',
  attendee_name: 'Ada Lovelace',
  attendee_email: 'ada@example.com',
  attendee_secondary_email: 'ada@personal.example',
  attendee_phone: '+15551234567',
  phone_verified: true,
  phone_verification_required: true,
  attendee_organization: 'UC Merced',
  registered_at: '',
  ticket_email_sent_at: '2026-01-01T00:00:00Z',
  ticket_email_error: '',
  barcode_format: 'png',
  barcode_image: 'data:image/png;base64,abc',
  event: {
    id: 'event-1',
    name: 'Demo Day',
    slug: 'demo-day',
    date: '2026-05-01',
    location: 'Campus',
    description: 'Project showcase',
  },
  ticket: {
    id: 'ticket-1',
    name: 'General Admission',
  },
  answers: [],
};

describe('event registration states', () => {
  beforeEach(() => {
    vi.mocked(resendTicketEmail).mockReset();
  });

  it('renders loading and fatal error states', () => {
    const {unmount} = render(<LoadingState error={null} />);
    expect(screen.getByText('Loading event details...')).toBeInTheDocument();

    unmount();
    render(<LoadingState error="Event unavailable" />);
    expect(screen.getByRole('heading', {name: 'Event Registration'})).toBeInTheDocument();
    expect(screen.getByText('Event unavailable')).toBeInTheDocument();
  });

  it('renders completed registrations and resends confirmation email', async () => {
    vi.mocked(resendTicketEmail).mockResolvedValue(undefined);

    render(
      <MemoryRouter>
        <DoneState registration={registration} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {name: "You're Registered!"})).toBeInTheDocument();
    expect(screen.getByText('I2G-123')).toBeInTheDocument();
    expect(screen.getByText(/ada@personal.example/)).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'View My Account'})).toHaveAttribute('href', '/account');

    fireEvent.click(screen.getByRole('button', {name: 'Resend Confirmation Email'}));

    await waitFor(() => {
      expect(resendTicketEmail).toHaveBeenCalledWith('registration-1');
    });
    expect(await screen.findByText('Email sent successfully.')).toBeInTheDocument();
  });

  it('shows a resend failure message', async () => {
    vi.mocked(resendTicketEmail).mockRejectedValue(new Error('failed'));

    render(
      <MemoryRouter>
        <DoneState registration={{...registration, ticket_email_sent_at: null, attendee_secondary_email: ''}} />
      </MemoryRouter>,
    );

    expect(screen.queryByText(/confirmation email was sent/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Resend Confirmation Email'}));

    expect(await screen.findByText('Failed to send email. Please try again.')).toBeInTheDocument();
  });

  it('formats dates and extracts bounded API error messages', () => {
    expect(formatEventDate('2026-05-01')).toContain('May');
    expect(getRegistrationErrorMessage({response: {data: {message: 'Ticket sold out'}}})).toBe('Ticket sold out');
    expect(getRegistrationErrorMessage({response: {data: {email: ['Email is invalid']}}})).toBe('Email is invalid');
    expect(getRegistrationErrorMessage({response: {data: {detail: 'x'.repeat(301)}}})).toBe(
      'An unexpected error occurred. Please try again.',
    );
  });
});
