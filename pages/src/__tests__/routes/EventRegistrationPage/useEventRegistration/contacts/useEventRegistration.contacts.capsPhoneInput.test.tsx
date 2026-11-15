import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {EventRegistrationOptions} from '@/features/events/api';
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

  it('caps phone input and resets verification state', async () => {
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('email'));

    act(() => {
      result.current.handlePhoneChange('12345678901234');
    });

    expect(result.current.attendeePhone).toBe('1234567890');
    expect(result.current.phoneVerified).toBe(false);
  });

  it('derives a phone validation error for changed digits', async () => {
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('email'));

    act(() => {
      result.current.handlePhoneChange('12345');
    });

    expect(result.current.phoneError).toBe('US phone numbers must be exactly 10 digits.');
  });

  it('uses explicit secondary email metadata instead of the legacy email array', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({
      allow_secondary_email: true,
      member_emails: ['ada@example.com', 'legacy@example.com'],
      member_secondary_email: {email_address: 'current@example.com', verified: false},
    }));
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));
    expect(result.current.attendeeSecondaryEmail).toBe('current@example.com');
    expect(result.current.secondaryEmailVerified).toBe(false);
  });

  it('does not mistake a secondary-only member email for a primary address', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({
      allow_secondary_email: true, verify_secondary_email: true,
      member_primary_email: '', member_emails: ['personal@example.com'],
      member_secondary_email: {email_address: 'personal@example.com', verified: false},
    }));
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));
    expect(result.current.primaryEmail).toBe('');
    expect(result.current.attendeeSecondaryEmail).toBe('personal@example.com');
    await act(async () => { await result.current.handleSendSecondaryEmailCode(); });
    expect(mockSendSecondaryEmailCode).toHaveBeenCalledWith('personal@example.com', 'demo-day');
  });

  it('prefills legacy secondary email responses without claiming verification', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    const legacyOptions: Partial<EventRegistrationOptions> = formOptions({allow_secondary_email: true, member_emails: ['ada@example.com', 'personal@example.com']});
    delete legacyOptions.member_secondary_email;
    mockFetchRegistrationOptions.mockResolvedValue(legacyOptions);
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));
    expect(result.current.primaryEmail).toBe('ada@example.com');
    expect(result.current.attendeeSecondaryEmail).toBe('personal@example.com');
    expect(result.current.secondaryEmailVerified).toBe(false);
  });

  it('sends and verifies a secondary email without updating the account, then submits the receipt', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({allow_secondary_email: true, verify_secondary_email: true}));
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));
    act(() => result.current.handleSecondaryEmailChange(' PERSONAL@EXAMPLE.COM '));
    await act(async () => { await result.current.handleSendSecondaryEmailCode(); });
    expect(mockSendSecondaryEmailCode).toHaveBeenCalledWith('personal@example.com', 'demo-day');
    act(() => result.current.setSecondaryEmailCode('123456'));
    await act(async () => { await result.current.handleVerifySecondaryEmailCode(); });
    expect(mockVerifySecondaryEmailCode).toHaveBeenCalledWith('personal@example.com', '123456', 'email-challenge-1', 'demo-day');
    expect(result.current.secondaryEmailVerified).toBe(true);
    expect(mockUpdateProfileFields).not.toHaveBeenCalled();
    expect(mockCreateRegistration).not.toHaveBeenCalled();
    act(() => result.current.setSelectedTicketId('ticket-1'));
    await act(async () => { await result.current.handleRegistrationSubmit(fakeEvent()); });
    expect(mockCreateRegistration).toHaveBeenCalledWith(expect.objectContaining({
      attendee_secondary_email: 'personal@example.com',
      secondary_email_verification_challenge_id: 'email-challenge-1',
      secondary_email_verification_token: 'email-proof-1',
    }));
  });
});
