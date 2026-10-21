import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {FormEvent, ReactNode} from 'react';

import type {EventRegistrationOptions, Registration} from '@/features/events/api';
import {useEventRegistration} from '@/routes/EventRegistrationPage/useEventRegistration';

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

const demoEvent = {
  id: 'event-1',
  name: 'Demo Day',
  slug: 'demo-day',
  date: '2026-05-01',
  location: 'Campus',
  description: 'Event description',
  registration: null,
};

const baseOptions: EventRegistrationOptions = {
  id: 'event-1',
  name: 'Demo Day',
  slug: 'demo-day',
  date: '2026-05-01',
  location: 'Campus',
  description: 'Event description',
  allow_secondary_email: false,
  collect_phone: false,
  verify_phone: false,
  require_phone: false,
  verify_secondary_email: false,
  require_secondary_email: false,
  tickets: [{id: 'ticket-1', name: 'General Admission'}],
  questions: [],
  registration: null,
  member_emails: [],
  member_secondary_email: null,
  member_profile: null,
  member_phone: null,
  phone_regions: [{code: '1-US', label: 'United States'}],
};

const memberProfile = {
  first_name: 'Ada',
  middle_name: '',
  last_name: 'Lovelace',
  organization: 'Acme',
  title: 'Engineer',
};

const registrationFixture = (overrides: Partial<Registration> = {}): Registration => ({
  id: 'registration-1',
  ticket_code: 'I2G-TEST',
  attendee_first_name: 'Ada',
  attendee_last_name: 'Lovelace',
  attendee_name: 'Ada Lovelace',
  attendee_email: 'ada@example.com',
  attendee_secondary_email: '',
  attendee_phone: '',
  phone_verified: false,
  secondary_email_verified: false,
  phone_verification_required: false,
  attendee_organization: 'Acme',
  registered_at: '2026-05-01T12:00:00Z',
  ticket_email_sent_at: null,
  ticket_email_error: '',
  barcode_format: 'PDF417',
  barcode_image: 'data:image/png;base64,test',
  event: {...demoEvent},
  ticket: {id: 'ticket-1', name: 'General Admission'},
  answers: [],
  ...overrides,
});

const authenticated = {
  isAuthenticated: true,
  requiresProfileCompletion: false,
  requestEmailAuthCode,
  verifyEmailAuthCode,
  requestPhoneAuthCode,
  verifyPhoneAuthCode,
};

const formOptions = (overrides: Partial<EventRegistrationOptions> = {}): EventRegistrationOptions => ({
  ...baseOptions,
  member_emails: ['ada@example.com'],
  member_secondary_email: null,
  member_profile: {...memberProfile},
  ...overrides,
});

const wrapper = ({children}: {children?: ReactNode}) => (
  <MemoryRouter initialEntries={['/event-registration']}>{children}</MemoryRouter>
);

const fakeEvent = () => ({preventDefault: vi.fn()}) as unknown as FormEvent;

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
    verifyEmailAuthCode.mockResolvedValue({
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: 'member-1', email: 'ada@example.com'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
    });
    verifyPhoneAuthCode.mockResolvedValue({
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: 'member-1', phone: '+12025550123'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
    });
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

  it('ignores invalid phone send requests', async () => {
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('email'));

    await act(async () => {
      await result.current.handleSendPhoneCode();
    });

    expect(mockSendPhoneCode).not.toHaveBeenCalled();
  });

  it('sends and verifies a phone code', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({collect_phone: true, verify_phone: true}));

    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));

    act(() => {
      result.current.handlePhoneChange('2025550123');
    });
    await act(async () => {
      await result.current.handleSendPhoneCode();
    });
    expect(mockSendPhoneCode).toHaveBeenCalledWith('2025550123', '1-US', 'demo-day');
    expect(result.current.phoneCodeSent).toBe(true);

    act(() => {
      result.current.setPhoneCode('123456');
    });
    await act(async () => {
      await result.current.handleVerifyPhoneCode();
    });
    expect(mockVerifyPhoneCode).toHaveBeenCalledWith('2025550123', '123456', 'challenge-1', 'demo-day');
    expect(result.current.phoneVerified).toBe(true);
  });

  it('surfaces a phone send error', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({collect_phone: true, verify_phone: true}));
    mockSendPhoneCode.mockRejectedValue({response: {data: {detail: 'Send failed.'}}});

    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));

    act(() => {
      result.current.handlePhoneChange('2025550123');
    });
    await act(async () => {
      await result.current.handleSendPhoneCode();
    });

    expect(result.current.error).toBe('Send failed.');
  });

  it('surfaces a phone verify error', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({collect_phone: true, verify_phone: true}));
    mockVerifyPhoneCode.mockRejectedValue({response: {data: {detail: 'Verify failed.'}}});

    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));

    act(() => {
      result.current.handlePhoneChange('2025550123');
    });
    await act(async () => {
      await result.current.handleSendPhoneCode();
    });
    act(() => {
      result.current.setPhoneCode('123456');
    });
    await act(async () => {
      await result.current.handleVerifyPhoneCode();
    });

    expect(result.current.error).toBe('Verify failed.');
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
