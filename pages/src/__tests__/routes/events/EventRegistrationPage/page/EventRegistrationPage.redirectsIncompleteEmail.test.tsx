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
      expect(requestEmailAuthCode).toHaveBeenCalledWith('ada@example.com', 'event_registration', 'demo-day');
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
});
