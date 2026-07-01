import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {EventRegistrationPage} from '../EventRegistrationPage';

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

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
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

    mockFetchRegistrationEvents.mockResolvedValue([
      {
        id: 'event-1',
        name: 'Demo Day',
        slug: 'demo-day',
        date: '2026-05-01',
        location: 'Campus',
        description: 'Event description',
        registration: null,
      },
    ]);

    mockFetchRegistrationOptions.mockResolvedValue({
      id: 'event-1',
      name: 'Demo Day',
      slug: 'demo-day',
      date: '2026-05-01',
      location: 'Campus',
      description: 'Event description',
      allow_secondary_email: false,
      collect_phone: false,
      verify_phone: false,
      tickets: [{id: 'ticket-1', name: 'General Admission'}],
      questions: [],
      registration: null,
      member_emails: [],
      member_profile: null,
      member_phone: null,
      phone_regions: [{code: '1-US', label: 'United States'}],
    });

    requestEmailAuthCode.mockResolvedValue({message: 'ok'});
    verifyEmailAuthCode.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: 'member-1', email: 'ada@example.com'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
    });
    requestPhoneAuthCode.mockResolvedValue({message: 'ok'});
    mockUpdateProfileFields.mockResolvedValue({});
    mockCreateRegistration.mockResolvedValue({
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
        id: 'event-1',
        name: 'Demo Day',
        slug: 'demo-day',
        date: '2026-05-01',
        location: 'Campus',
        description: 'Event description',
      },
      ticket: {id: 'ticket-1', name: 'General Admission'},
      answers: [],
    });
    verifyPhoneAuthCode.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: 'member-1', phone: '+12025550123'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
    });
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

  it('redirects incomplete email-auth signups to complete-profile before showing the form', async () => {
    render(
      <MemoryRouter initialEntries={['/event-registration']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByLabelText('Email or Phone');

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'ada@example.com'}});
    fireEvent.submit(screen.getByRole('button', {name: 'Continue'}).closest('form')!);

    await waitFor(() => {
      expect(requestEmailAuthCode).toHaveBeenCalledWith('ada@example.com', 'event_registration');
    });

    const codeInput = await screen.findByLabelText('Verification Code');
    fireEvent.change(codeInput, {target: {value: '123456'}});
    fireEvent.submit(screen.getByRole('button', {name: 'Verify Code'}).closest('form')!);

    await waitFor(() => {
      expect(verifyEmailAuthCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fevent-registration%3Fevent%3Ddemo-day', {replace: true});
    });
  });

  it('redirects authenticated members with incomplete names before loading the form', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      requiresProfileCompletion: true,
      requestEmailAuthCode,
      verifyEmailAuthCode,
    });

    render(
      <MemoryRouter initialEntries={['/event-registration']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fevent-registration', {replace: true});
    });

    expect(mockFetchRegistrationOptions).not.toHaveBeenCalled();
  });

  it('preserves an event deep link when an authenticated member must complete their profile', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      requiresProfileCompletion: true,
      requestEmailAuthCode,
      verifyEmailAuthCode,
    });

    render(
      <MemoryRouter initialEntries={['/event-registration?event=fall-showcase']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        '/complete-profile?returnTo=%2Fevent-registration%3Fevent%3Dfall-showcase',
        {replace: true},
      );
    });

    expect(mockFetchRegistrationOptions).not.toHaveBeenCalled();
  });

  it('renders multiple open events and loads the selected event options', async () => {
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
        registration: null,
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
      tickets: [{id: 'ticket-fall', name: 'General Admission'}],
      questions: [],
      registration: null,
      member_emails: [],
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

    await screen.findByRole('heading', {name: 'Spring Showcase'});
    fireEvent.click(screen.getAllByRole('button', {name: 'Register'})[1]);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/event-registration?event=fall-showcase');
    });
  });

  it('submits registration with the selected event slug', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      requiresProfileCompletion: false,
      requestEmailAuthCode,
      verifyEmailAuthCode,
      requestPhoneAuthCode,
      verifyPhoneAuthCode,
    });
    mockFetchRegistrationEvents.mockResolvedValue([
      {
        id: 'event-fall',
        name: 'Fall Showcase',
        slug: 'fall-showcase',
        date: '2026-10-01',
        location: 'Conference Center',
        description: 'Fall event',
        registration: null,
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
      tickets: [{id: 'ticket-fall', name: 'General Admission'}],
      questions: [],
      registration: null,
      member_emails: ['ada@example.com'],
      member_profile: {
        first_name: 'Ada',
        middle_name: '',
        last_name: 'Lovelace',
        organization: 'Acme',
        title: 'Engineer',
      },
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

    await screen.findByRole('heading', {name: 'Fall Showcase'});
    fireEvent.click(screen.getByRole('radio', {name: 'General Admission'}));
    fireEvent.submit(screen.getByRole('button', {name: 'Register'}).closest('form')!);

    await waitFor(() => {
      expect(mockCreateRegistration).toHaveBeenCalledWith(expect.objectContaining({
        event_slug: 'fall-showcase',
        ticket_id: 'ticket-fall',
      }));
    });
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
      tickets: [{id: 'ticket-fall', name: 'General Admission'}],
      questions: [],
      registration: existingRegistration,
      member_emails: [],
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
    fireEvent.click(screen.getByRole('button', {name: 'View Other Events'}));

    await screen.findByRole('heading', {name: 'Spring Showcase'});
  });
});
