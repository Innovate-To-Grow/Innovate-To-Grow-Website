import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {EventRegistrationPage} from '@/routes/EventRegistrationPage/EventRegistrationPage';
import {
  createdRegistration,
  emailSignIn,
  phoneSignIn,
  registrationEvents,
  registrationOptions,
} from '@/__tests__/routes/EventRegistrationPage/page/eventRegistrationPageFixtures';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();
const mockUpdateProfileFields = vi.fn();
const mockCreateRegistration = vi.fn();
const mockFetchRegistrationEvents = vi.fn();
const mockFetchRegistrationOptions = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
    updateProfileFields: (...args: unknown[]) => mockUpdateProfileFields(...args),
  };
});

vi.mock('@/features/events/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/events/api')>('@/features/events/api');
  return {
    ...actual,
    fetchRegistrationEvents: (...args: unknown[]) => mockFetchRegistrationEvents(...args),
    fetchRegistrationOptions: (...args: unknown[]) => mockFetchRegistrationOptions(...args),
    createRegistration: (...args: unknown[]) => mockCreateRegistration(...args),
    sendPhoneCode: vi.fn(),
    verifyPhoneCode: vi.fn(),
  };
});

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('EventRegistrationPage', () => {
  const requestEmailAuthCode = vi.fn();
  const verifyEmailAuthCode = vi.fn();
  const requestPhoneAuthCode = vi.fn();
  const verifyPhoneAuthCode = vi.fn();

  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockUpdateProfileFields.mockReset();
    mockCreateRegistration.mockReset();
    mockFetchRegistrationEvents.mockReset();
    mockFetchRegistrationOptions.mockReset();
    requestEmailAuthCode.mockReset();
    verifyEmailAuthCode.mockReset();
    requestPhoneAuthCode.mockReset();
    verifyPhoneAuthCode.mockReset();

    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      requiresProfileCompletion: false,
      requestEmailAuthCode,
      verifyEmailAuthCode,
      requestPhoneAuthCode,
      verifyPhoneAuthCode,
    });

    mockFetchRegistrationEvents.mockResolvedValue(registrationEvents());

    mockFetchRegistrationOptions.mockResolvedValue(registrationOptions());

    requestEmailAuthCode.mockResolvedValue({message: 'ok'});
    verifyEmailAuthCode.mockResolvedValue(emailSignIn());
    requestPhoneAuthCode.mockResolvedValue({message: 'ok'});
    mockUpdateProfileFields.mockResolvedValue({});
    mockCreateRegistration.mockResolvedValue(createdRegistration());
    verifyPhoneAuthCode.mockResolvedValue(phoneSignIn());
  });

  it('routes a phone entry to the SMS-code flow with the event_registration source', async () => {
    render(
      <MemoryRouter initialEntries={['/event-registration']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByLabelText('Email or Phone');
    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: '(202) 555-0123'}});
    fireEvent.submit(screen.getByRole('button', {name: 'Continue'}).closest('form')!);

    await waitFor(() => {
      expect(requestPhoneAuthCode).toHaveBeenCalledWith('2025550123', '1-US', 'event_registration');
    });
    expect(requestEmailAuthCode).not.toHaveBeenCalled();
  });

  it('shows the progress row with the verify step current for a signed-out visitor', async () => {
    render(
      <MemoryRouter initialEntries={['/event-registration']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByLabelText('Email or Phone');
    const items = within(screen.getByRole('list', {name: 'Registration steps'})).getAllByRole('listitem');
    expect(items.map((item) => item.querySelector('.event-reg-step-label')?.textContent)).toEqual([
      'Choose event',
      'Verify',
      'Your details',
      'Ticket',
    ]);
    expect(items[0]).toHaveClass('is-complete');
    expect(items[1]).toHaveClass('is-current');
    expect(items[1]).toHaveAttribute('aria-current', 'step');
    expect(items[2]).toHaveClass('is-upcoming');
    expect(items[2]).not.toHaveAttribute('aria-current');
  });

  it('hides the progress row while the event list is still loading', () => {
    mockFetchRegistrationEvents.mockReturnValue(new Promise(() => {}));

    render(
      <MemoryRouter initialEntries={['/event-registration']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole('status')).toHaveTextContent('Loading event details...');
    expect(screen.queryByRole('list', {name: 'Registration steps'})).toBeNull();
  });

  it('renders the selected event date range in the registration header', async () => {
    mockFetchRegistrationOptions.mockResolvedValue({
      id: 'event-1',
      name: 'Demo Day',
      slug: 'demo-day',
      date: '2026-05-01',
      end_date: '2026-05-03',
      location: 'Campus',
      description: 'Event description',
      allow_secondary_email: false,
      collect_phone: false,
      verify_phone: false,
      require_phone: false,
      verify_secondary_email: false,
      require_secondary_email: false,
      tickets: [{id: 'ticket-1', name: 'General Admission'}],
      questions: [],
      registration: null,
      member_emails: [],
      member_secondary_email: null,
      member_profile: null,
      member_phone: null,
      phone_regions: [{code: '1-US', label: 'United States'}],
    });

    render(
      <MemoryRouter initialEntries={['/event-registration']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Friday, May 1 – Sunday, May 3, 2026')).toBeInTheDocument();
  });
});
