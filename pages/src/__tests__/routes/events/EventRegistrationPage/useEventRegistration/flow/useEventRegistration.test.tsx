import {cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {useEventRegistration} from '@/routes/events/EventRegistrationPage/page/useEventRegistration';
import {baseOptions, demoEvent, emailSignIn, formOptions, phoneSignIn, registrationFixture, wrapper} from '@/__tests__/routes/events/EventRegistrationPage/useEventRegistration/fixtures/useEventRegistrationFixtures';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();
const mockUpdateProfileFields = vi.fn();
const mockCreateRegistration = vi.fn();
const mockFetchRegistrationEvents = vi.fn();
const mockFetchRegistrationOptions = vi.fn();
const mockSendPhoneCode = vi.fn();
const mockVerifyPhoneCode = vi.fn();
const mockSendSecondaryEmailCode = vi.fn();
const mockVerifySecondaryEmailCode = vi.fn();

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
    sendPhoneCode: (...args: unknown[]) => mockSendPhoneCode(...args),
    verifyPhoneCode: (...args: unknown[]) => mockVerifyPhoneCode(...args),
    sendSecondaryEmailCode: (...args: unknown[]) => mockSendSecondaryEmailCode(...args),
    verifySecondaryEmailCode: (...args: unknown[]) => mockVerifySecondaryEmailCode(...args),
  };
});

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const requestEmailAuthCode = vi.fn();
const verifyEmailAuthCode = vi.fn();
const requestPhoneAuthCode = vi.fn();
const verifyPhoneAuthCode = vi.fn();

const authenticated = {
  isAuthenticated: true,
  requiresProfileCompletion: false,
  requestEmailAuthCode,
  verifyEmailAuthCode,
  requestPhoneAuthCode,
  verifyPhoneAuthCode,
};

describe('useEventRegistration', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockUpdateProfileFields.mockReset();
    mockCreateRegistration.mockReset();
    mockFetchRegistrationEvents.mockReset();
    mockFetchRegistrationOptions.mockReset();
    mockSendPhoneCode.mockReset();
    mockVerifyPhoneCode.mockReset();
    mockSendSecondaryEmailCode.mockReset();
    mockVerifySecondaryEmailCode.mockReset();
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

    mockFetchRegistrationEvents.mockResolvedValue([{...demoEvent}]);
    mockFetchRegistrationOptions.mockResolvedValue({...baseOptions});
    requestEmailAuthCode.mockResolvedValue({message: 'ok'});
    requestPhoneAuthCode.mockResolvedValue({message: 'ok'});
    verifyEmailAuthCode.mockResolvedValue(emailSignIn());
    verifyPhoneAuthCode.mockResolvedValue(phoneSignIn());
    mockUpdateProfileFields.mockResolvedValue({});
    mockCreateRegistration.mockResolvedValue(registrationFixture());
    mockSendPhoneCode.mockResolvedValue({detail: 'sent', phone: '2025550123', challenge_id: 'challenge-1'});
    mockVerifyPhoneCode.mockResolvedValue({detail: 'verified', verified: true, phone: '2025550123', challenge_id: 'challenge-1'});
    mockSendSecondaryEmailCode.mockResolvedValue({email: 'personal@example.com', challenge_id: 'email-challenge-1'});
    mockVerifySecondaryEmailCode.mockResolvedValue({email: 'personal@example.com', verified: true, challenge_id: 'email-challenge-1', verification_token: 'email-proof-1'});
  });

  afterEach(() => {
    cleanup();
  });

  it('routes an unauthenticated visitor to the email step', async () => {
    const {result} = renderHook(() => useEventRegistration(), {wrapper});

    await waitFor(() => expect(result.current.step).toBe('email'));
    expect(mockFetchRegistrationOptions).toHaveBeenCalledWith('demo-day');
    expect(result.current.selectedEventSlug).toBe('demo-day');
  });

  it('prefills secondary email and a verified phone for an authenticated member', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({
      allow_secondary_email: true,
      collect_phone: true,
      member_emails: ['ada@example.com', 'personal@example.com'],
      member_secondary_email: {email_address: 'personal@example.com', verified: true},
      member_phone: {phone_number: '+12025550123', region: '1-US', verified: true},
    }));

    const {result} = renderHook(() => useEventRegistration(), {wrapper});

    await waitFor(() => expect(result.current.step).toBe('form'));
    expect(result.current.attendeeSecondaryEmail).toBe('personal@example.com');
    expect(result.current.secondaryEmailVerified).toBe(true);
    expect(result.current.attendeePhone).toBe('2025550123');
    expect(result.current.phoneVerified).toBe(true);
    expect(result.current.phoneCodeSent).toBe(true);
  });

  it('redirects to complete-profile when the member is missing names', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({
      member_profile: {first_name: 'Ada', middle_name: '', last_name: '', organization: 'Acme', title: ''},
    }));

    renderHook(() => useEventRegistration(), {wrapper});

    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith(
        '/complete-profile?returnTo=%2Fevent-registration%3Fevent%3Ddemo-day',
        {replace: true},
      ),
    );
  });

  it('falls back to the email step on a 401 options error', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockRejectedValue({response: {status: 401}});

    const {result} = renderHook(() => useEventRegistration(), {wrapper});

    await waitFor(() => expect(result.current.step).toBe('email'));
  });

  it('shows a friendly message when the event is not accepting registrations', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockRejectedValue({
      response: {data: {detail: 'This event is no longer accepting registrations.'}},
    });

    const {result} = renderHook(() => useEventRegistration(), {wrapper});

    await waitFor(() => expect(result.current.step).toBe('select'));
    expect(result.current.error).toBe('This event is not currently accepting registrations.');
  });

  it('surfaces a fatal boot error when event list loading fails', async () => {
    mockFetchRegistrationEvents.mockRejectedValue({
      response: {data: {detail: 'Backend unavailable.'}},
    });

    const {result} = renderHook(() => useEventRegistration(), {wrapper});

    await waitFor(() => expect(result.current.error).toBe('Backend unavailable.'));
    expect(result.current.step).toBe('loading');
  });

  it('surfaces options errors for unauthenticated visitors and stays on email', async () => {
    mockFetchRegistrationOptions.mockRejectedValue({
      response: {data: {detail: 'No options available.'}},
    });

    const {result} = renderHook(() => useEventRegistration(), {wrapper});

    await waitFor(() => expect(result.current.step).toBe('email'));
    expect(result.current.error).toBe('No options available.');
  });
});
