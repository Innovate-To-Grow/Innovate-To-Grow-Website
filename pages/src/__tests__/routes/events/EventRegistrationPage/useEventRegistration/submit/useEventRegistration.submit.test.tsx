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

describe('useEventRegistration — submitting a registration', () => {
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

  it('syncs the profile and creates the registration', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions());

    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));

    act(() => {
      result.current.setSelectedTicketId('ticket-1');
      result.current.setAttendeeFirstName('Grace');
    });
    await act(async () => {
      await result.current.handleRegistrationSubmit(fakeEvent());
    });

    expect(mockUpdateProfileFields).toHaveBeenCalledWith({
      first_name: 'Grace',
      middle_name: '',
      last_name: 'Lovelace',
      organization: 'Acme',
      title: 'Engineer',
    });
    expect(mockCreateRegistration).toHaveBeenCalledWith(expect.objectContaining({
      event_slug: 'demo-day',
      ticket_id: 'ticket-1',
      attendee_first_name: 'Grace',
    }));
  });

  it('maps non-empty answers into the registration payload', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions());

    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));

    act(() => {
      result.current.setSelectedTicketId('ticket-1');
      result.current.setAnswers({q1: 'None', q2: '   '});
    });
    await act(async () => {
      await result.current.handleRegistrationSubmit(fakeEvent());
    });

    expect(mockCreateRegistration).toHaveBeenCalledWith(expect.objectContaining({
      answers: [{question_id: 'q1', answer: 'None'}],
    }));
  });

  it('surfaces registration submission errors', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions());
    mockCreateRegistration.mockRejectedValue({response: {data: {detail: 'Submit failed.'}}});

    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));

    act(() => {
      result.current.setSelectedTicketId('ticket-1');
    });
    await act(async () => {
      await result.current.handleRegistrationSubmit(fakeEvent());
    });

    expect(result.current.error).toBe('Submit failed.');
  });

  it('recovers from a 409 registration conflict', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions());
    const existing = registrationFixture({id: 'registration-existing'});
    mockCreateRegistration.mockRejectedValue({
      response: {status: 409, data: {registration: existing}},
    });

    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));

    act(() => {
      result.current.setSelectedTicketId('ticket-1');
    });
    await act(async () => {
      await result.current.handleRegistrationSubmit(fakeEvent());
    });

    expect(result.current.step).toBe('done');
    expect(result.current.registration?.id).toBe('registration-existing');
  });
});
