import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {useEventRegistration} from '@/routes/EventRegistrationPage/useEventRegistration';
import {baseOptions, demoEvent, emailSignIn, fakeEvent, formOptions, phoneSignIn, registrationFixture, wrapper} from '@/__tests__/routes/EventRegistrationPage/useEventRegistration/fixtures/useEventRegistrationFixtures';

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

describe('useEventRegistration — contact verification', () => {
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

  it('ignores an in-flight email verification when switching events', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    const secondEvent = {...demoEvent, id: 'event-2', slug: 'second-event'};
    mockFetchRegistrationEvents.mockResolvedValue([{...demoEvent}, secondEvent]);
    mockFetchRegistrationOptions.mockImplementation((slug) => Promise.resolve(formOptions({slug, allow_secondary_email: true, verify_secondary_email: true})));
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('select'));
    act(() => result.current.handleSelectEvent('demo-day'));
    await waitFor(() => expect(result.current.step).toBe('form'));
    act(() => result.current.handleSecondaryEmailChange('personal@example.com'));
    await act(async () => { await result.current.handleSendSecondaryEmailCode(); });
    act(() => result.current.setSecondaryEmailCode('123456'));
    let resolveRequest!: (value: unknown) => void;
    mockVerifySecondaryEmailCode.mockReturnValueOnce(new Promise((resolve) => { resolveRequest = resolve; }));
    let pending!: Promise<void>;
    act(() => { pending = result.current.handleVerifySecondaryEmailCode(); });
    act(() => result.current.handleSelectEvent('second-event'));
    await waitFor(() => expect(result.current.options?.slug).toBe('second-event'));
    await act(async () => {
      resolveRequest({email: 'personal@example.com', verified: true, challenge_id: 'obsolete', verification_token: 'obsolete'});
      await pending;
    });
    expect(result.current.attendeeSecondaryEmail).toBe('');
    expect(result.current.secondaryEmailVerified).toBe(false);
    expect(result.current.secondaryEmailCodeSent).toBe(false);
  });

  it.each(['phone', 'secondary email'] as const)('allows reverification after the server rejects an expired %s receipt', async (contact) => {
    const isPhone = contact === 'phone';
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({
      collect_phone: true, verify_phone: true, allow_secondary_email: true, verify_secondary_email: true,
    }));
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));
    act(() => {
      result.current.setSelectedTicketId('ticket-1');
      if (isPhone) result.current.handlePhoneChange('2025550123');
      else result.current.handleSecondaryEmailChange('personal@example.com');
    });
    await act(async () => {
      if (isPhone) await result.current.handleSendPhoneCode();
      else await result.current.handleSendSecondaryEmailCode();
    });
    act(() => {
      if (isPhone) result.current.setPhoneCode('123456');
      else result.current.setSecondaryEmailCode('123456');
    });
    await act(async () => {
      if (isPhone) await result.current.handleVerifyPhoneCode();
      else await result.current.handleVerifySecondaryEmailCode();
    });
    mockCreateRegistration.mockRejectedValueOnce({response: {status: 400, data: {
      detail: 'Please verify this contact again.',
      code: isPhone ? 'phone_verification_required' : 'secondary_email_verification_required',
    }}});
    await act(async () => { await result.current.handleRegistrationSubmit(fakeEvent()); });
    expect(result.current.error).toBe('Please verify this contact again.');
    expect(isPhone ? result.current.phoneVerified : result.current.secondaryEmailVerified).toBe(false);
    expect(isPhone ? result.current.phoneCodeSent : result.current.secondaryEmailCodeSent).toBe(false);
    expect(isPhone ? result.current.attendeePhone : result.current.attendeeSecondaryEmail).toBe(isPhone ? '2025550123' : 'personal@example.com');
    await act(async () => {
      if (isPhone) await result.current.handleSendPhoneCode();
      else await result.current.handleSendSecondaryEmailCode();
    });
    expect(isPhone ? mockSendPhoneCode : mockSendSecondaryEmailCode).toHaveBeenCalledTimes(2);
  });
});
