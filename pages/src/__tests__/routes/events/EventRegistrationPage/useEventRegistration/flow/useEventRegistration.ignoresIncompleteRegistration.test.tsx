import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {EventRegistrationOptions} from '@/features/events/api';
import {useEventRegistration} from '@/routes/events/EventRegistrationPage/page/useEventRegistration';
import {baseOptions, demoEvent, emailSignIn, fakeEvent, formOptions, phoneSignIn, registrationFixture, wrapper} from '@/__tests__/routes/events/EventRegistrationPage/useEventRegistration/fixtures/useEventRegistrationFixtures';

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

  it('ignores incomplete registration submissions', async () => {
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('email'));

    await act(async () => {
      await result.current.handleRegistrationSubmit(fakeEvent());
    });

    expect(mockCreateRegistration).not.toHaveBeenCalled();
  });

  it('ignores old event options while the next event list is still loading', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    const eventList = [{...demoEvent}, {...demoEvent, id: 'event-2', slug: 'second-event'}];
    mockFetchRegistrationEvents.mockResolvedValue(eventList);
    let resolveOldOptions!: (value: EventRegistrationOptions) => void;
    const oldOptions = new Promise<EventRegistrationOptions>((resolve) => { resolveOldOptions = resolve; });
    mockFetchRegistrationOptions.mockImplementation((slug) => slug === 'demo-day'
      ? oldOptions : Promise.resolve(formOptions({slug, allow_secondary_email: true})));
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('select'));
    act(() => result.current.handleSelectEvent('demo-day'));
    await waitFor(() => expect(mockFetchRegistrationOptions).toHaveBeenCalledWith('demo-day'));
    let resolveEventList!: (value: typeof eventList) => void;
    mockFetchRegistrationEvents.mockReturnValueOnce(new Promise((resolve) => { resolveEventList = resolve; }));
    act(() => result.current.handleSelectEvent('second-event'));
    await waitFor(() => expect(mockFetchRegistrationEvents).toHaveBeenCalledTimes(3));
    await act(async () => {
      resolveOldOptions(formOptions({allow_secondary_email: true, member_secondary_email: {email_address: 'old@example.com', verified: true}}));
      await oldOptions;
    });
    expect(result.current.step).toBe('loading');
    expect(result.current.options).toBeNull();
    expect(result.current.secondaryEmailVerified).toBe(false);
    await act(async () => { resolveEventList(eventList); });
    await waitFor(() => expect(result.current.options?.slug).toBe('second-event'));
    expect(result.current.attendeeSecondaryEmail).toBe('');
  });
});
