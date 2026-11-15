import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
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

describe('EventRegistrationPage — the registration form', () => {
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

  it('returns from a registered event confirmation to the open event list', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      requiresProfileCompletion: false,
      requestEmailAuthCode,
      verifyEmailAuthCode,
      requestPhoneAuthCode,
      verifyPhoneAuthCode,
    });
    const existingRegistration = {
      id: 'registration-fall',
      ticket_code: 'I2G-FALL',
      attendee_first_name: 'Ada',
      attendee_last_name: 'Lovelace',
      attendee_name: 'Ada Lovelace',
      attendee_email: 'ada@example.com',
      attendee_secondary_email: '',
      attendee_phone: '',
      phone_verified: false,
      secondary_email_verified: false,
      phone_verification_required: false,
      attendee_organization: 'Acme',
      registered_at: '2026-10-01T12:00:00Z',
      ticket_email_sent_at: null,
      ticket_email_error: '',
      barcode_format: 'PDF417',
      barcode_image: 'data:image/png;base64,test',
      event: {
        id: 'event-fall',
        name: 'Fall Showcase',
        slug: 'fall-showcase',
        date: '2026-10-01',
        end_date: '2026-10-03',
        location: 'Conference Center',
        description: 'Fall event',
      },
      ticket: {id: 'ticket-fall', name: 'General Admission'},
      answers: [],
    };
    mockFetchRegistrationEvents.mockResolvedValue([
      {
        id: 'event-spring',
        name: 'Spring Showcase',
        slug: 'spring-showcase',
        date: '2026-05-01',
        location: 'Campus',
        description: 'Spring event',
        registration: null,
      },
      {
        id: 'event-fall',
        name: 'Fall Showcase',
        slug: 'fall-showcase',
        date: '2026-10-01',
        location: 'Conference Center',
        description: 'Fall event',
        registration: existingRegistration,
      },
    ]);
    mockFetchRegistrationOptions.mockResolvedValue({
      id: 'event-fall',
      name: 'Fall Showcase',
      slug: 'fall-showcase',
      date: '2026-10-01',
      location: 'Conference Center',
      description: 'Fall event',
      allow_secondary_email: false,
      collect_phone: false,
      verify_phone: false,
      require_phone: false,
      verify_secondary_email: false,
      require_secondary_email: false,
      tickets: [{id: 'ticket-fall', name: 'General Admission'}],
      questions: [],
      registration: existingRegistration,
      member_emails: [],
      member_secondary_email: null,
      member_profile: null,
      member_phone: null,
      phone_regions: [{code: '1-US', label: 'United States'}],
    });

    render(
      <MemoryRouter initialEntries={['/event-registration?event=fall-showcase']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByRole('heading', {name: "You're Registered!"});
    expect(screen.getByText('Thursday, October 1 – Saturday, October 3, 2026')).toBeInTheDocument();
    // The confirmation keeps the page title and marks the last step as current.
    expect(screen.getByRole('heading', {name: 'Event Registration', level: 1})).toBeInTheDocument();
    const doneSteps = within(screen.getByRole('list', {name: 'Registration steps'})).getAllByRole('listitem');
    expect(doneSteps[3]).toHaveAttribute('aria-current', 'step');
    expect(screen.getByRole('link', {name: 'View My Account'})).toHaveAttribute('href', '/account');
    fireEvent.click(screen.getByRole('button', {name: 'View Other Events'}));

    await screen.findByRole('heading', {name: 'Spring Showcase'});
  });
});
