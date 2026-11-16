import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {EventRegistrationPage} from '@/routes/events/EventRegistrationPage/page/EventRegistrationPage';
import {
  createdRegistration,
  emailSignIn,
  phoneSignIn,
  registrationEvents,
  registrationOptions,
} from '@/__tests__/routes/events/EventRegistrationPage/page/eventRegistrationPageFixtures';

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

  it('renders multiple open events and loads the selected event options', async () => {
    mockFetchRegistrationEvents.mockResolvedValue([
      {
        id: 'event-spring',
        name: 'Spring Showcase',
        slug: 'spring-showcase',
        date: '2026-05-01',
        end_date: '2026-05-03',
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
      require_phone: false,
      verify_secondary_email: false,
      require_secondary_email: false,
      tickets: [{id: 'ticket-fall', name: 'General Admission'}],
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

    await screen.findByRole('heading', {name: 'Spring Showcase'});
    expect(screen.getByText('Friday, May 1 – Sunday, May 3, 2026')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', {name: 'Register'})[1]);

    // Selection is a search-param change (no navigate) so it also works inside /_embed routes.
    await waitFor(() => {
      expect(mockFetchRegistrationOptions).toHaveBeenCalledWith('fall-showcase');
    });
    await screen.findByText(/Fall event/);
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('shows the fatal empty state when no events are open', async () => {
    mockFetchRegistrationEvents.mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={['/event-registration']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText('No event is currently accepting registrations.');
    expect(mockFetchRegistrationOptions).not.toHaveBeenCalled();
  });
});
