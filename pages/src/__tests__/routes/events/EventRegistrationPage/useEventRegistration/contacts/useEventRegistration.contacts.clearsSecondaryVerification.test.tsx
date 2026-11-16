import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
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

  it('clears secondary verification receipts on address change but preserves formatting-only changes', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({allow_secondary_email: true, verify_secondary_email: true}));
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));
    act(() => result.current.handleSecondaryEmailChange('personal@example.com'));
    await act(async () => { await result.current.handleSendSecondaryEmailCode(); });
    act(() => result.current.setSecondaryEmailCode('123456'));
    await act(async () => { await result.current.handleVerifySecondaryEmailCode(); });
    act(() => result.current.handleSecondaryEmailChange(' PERSONAL@EXAMPLE.COM '));
    expect(result.current.secondaryEmailVerified).toBe(true);
    act(() => result.current.handleSecondaryEmailChange('different@example.com'));
    expect(result.current.secondaryEmailVerified).toBe(false);
    expect(result.current.secondaryEmailCodeSent).toBe(false);
    expect(result.current.secondaryEmailCode).toBe('');
    act(() => {
      result.current.handleSecondaryEmailChange('');
      result.current.setSelectedTicketId('ticket-1');
    });
    await act(async () => { await result.current.handleRegistrationSubmit(fakeEvent()); });
    expect(mockCreateRegistration).toHaveBeenCalledWith(expect.objectContaining({
      attendee_secondary_email: undefined,
      secondary_email_verification_challenge_id: undefined,
      secondary_email_verification_token: undefined,
    }));
  });

  it.each(['send', 'verify'] as const)('surfaces secondary email %s failures', async (operation) => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({allow_secondary_email: true, verify_secondary_email: true}));
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));
    act(() => result.current.handleSecondaryEmailChange('personal@example.com'));
    if (operation === 'send') mockSendSecondaryEmailCode.mockRejectedValue({response: {data: {detail: 'Email send failed.'}}});
    await act(async () => { await result.current.handleSendSecondaryEmailCode(); });
    if (operation === 'verify') {
      mockVerifySecondaryEmailCode.mockRejectedValue({response: {data: {detail: 'Email verify failed.'}}});
      act(() => result.current.setSecondaryEmailCode('123456'));
      await act(async () => { await result.current.handleVerifySecondaryEmailCode(); });
    }
    expect(result.current.error).toBe(`Email ${operation} failed.`);
    expect(result.current.secondaryEmailVerified).toBe(false);
  });

  describe.each(['phone', 'secondary email'] as const)('%s asynchronous verification', (contact) => {
    it.each(['send', 'verify'] as const)('ignores a stale %s result after changing the contact', async (operation) => {
      mockUseAuth.mockReturnValue({...authenticated});
      mockFetchRegistrationOptions.mockResolvedValue(formOptions({collect_phone: true, verify_phone: true, allow_secondary_email: true, verify_secondary_email: true}));
      const {result} = renderHook(() => useEventRegistration(), {wrapper});
      await waitFor(() => expect(result.current.step).toBe('form'));
      const isPhone = contact === 'phone';
      const send = () => isPhone ? result.current.handleSendPhoneCode() : result.current.handleSendSecondaryEmailCode();
      const verify = () => isPhone ? result.current.handleVerifyPhoneCode() : result.current.handleVerifySecondaryEmailCode();
      act(() => {
        if (isPhone) result.current.handlePhoneChange('2025550123');
        else result.current.handleSecondaryEmailChange('personal@example.com');
      });
      if (operation === 'verify') {
        await act(async () => { await send(); });
        act(() => {
          if (isPhone) result.current.setPhoneCode('123456');
          else result.current.setSecondaryEmailCode('123456');
        });
      }
      let resolveRequest!: (value: unknown) => void;
      const deferred = new Promise((resolve) => { resolveRequest = resolve; });
      const mock = isPhone
        ? operation === 'send' ? mockSendPhoneCode : mockVerifyPhoneCode
        : operation === 'send' ? mockSendSecondaryEmailCode : mockVerifySecondaryEmailCode;
      mock.mockReturnValueOnce(deferred);
      let pending!: Promise<void>;
      act(() => { pending = operation === 'send' ? send() : verify(); });
      act(() => {
        if (isPhone) result.current.handlePhoneChange('4155550123');
        else result.current.handleSecondaryEmailChange('changed@example.com');
      });
      await act(async () => {
        resolveRequest({phone: '2025550123', email: 'personal@example.com', verified: true, challenge_id: 'obsolete', verification_token: 'obsolete'});
        await pending;
      });
      expect(isPhone ? result.current.phoneVerified : result.current.secondaryEmailVerified).toBe(false);
      expect(isPhone ? result.current.phoneCodeSent : result.current.secondaryEmailCodeSent).toBe(false);
    });
  });
});
