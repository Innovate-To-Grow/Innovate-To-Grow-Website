import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router';
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

  it('recovers from a stale event deep link by showing the open-event list', async () => {
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
    ]);

    render(
      <MemoryRouter initialEntries={['/event-registration?event=closed-event']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText('This event is not currently accepting registrations.');
    await screen.findByRole('heading', {name: 'Spring Showcase'});
    expect(screen.getByRole('button', {name: 'Register'})).toBeTruthy();
    expect(mockFetchRegistrationOptions).not.toHaveBeenCalled();
  });

  it('keeps event selection on the embed route without changing the pathname', async () => {
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

    const LocationProbe = () => {
      const location = useLocation();
      return <div data-testid="location-probe">{location.pathname + location.search}</div>;
    };

    render(
      <MemoryRouter initialEntries={['/_embed/reg-widget?hide-titles=1']}>
        <Routes>
          <Route
            path="/_embed/:embedSlug"
            element={
              <>
                <EventRegistrationPage />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByRole('heading', {name: 'Spring Showcase'});
    fireEvent.click(screen.getAllByRole('button', {name: 'Register'})[0]);

    await waitFor(() => {
      expect(screen.getByTestId('location-probe').textContent).toBe(
        '/_embed/reg-widget?hide-titles=1&event=spring-showcase',
      );
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('returns to the email step from the code step', async () => {
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
    await screen.findByLabelText('Verification Code');

    fireEvent.click(screen.getByRole('button', {name: 'Use a different email or phone'}));

    expect(screen.getByLabelText('Email or Phone')).toBeInTheDocument();
  });
});
