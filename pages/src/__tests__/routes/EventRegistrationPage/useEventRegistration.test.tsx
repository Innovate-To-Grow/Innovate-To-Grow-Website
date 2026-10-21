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

  it('rejects an invalid email or phone entry', async () => {
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('email'));

    act(() => {
      result.current.setEmail('not-an-email');
    });
    await act(async () => {
      await result.current.handleEmailSubmit(fakeEvent());
    });

    expect(result.current.error).toBe('Please enter a valid email address or 10-digit US phone number.');
    expect(requestEmailAuthCode).not.toHaveBeenCalled();
    expect(requestPhoneAuthCode).not.toHaveBeenCalled();
  });

  it('surfaces an email-code error from the email submit', async () => {
    requestEmailAuthCode.mockRejectedValue({response: {data: {detail: 'Rate limited.'}}});

    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('email'));

    act(() => {
      result.current.setEmail('ada@example.com');
    });
    await act(async () => {
      await result.current.handleEmailSubmit(fakeEvent());
    });

    expect(result.current.error).toBe('Rate limited.');
  });

  it('routes the phone flow back into options loading after verification', async () => {
    verifyPhoneAuthCode.mockResolvedValue({
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: 'member-1', phone: '+12025550123'},
      next_step: '',
      requires_profile_completion: false,
    });

    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('email'));

    act(() => {
      result.current.setEmail('(202) 555-0123');
    });
    await act(async () => {
      await result.current.handleEmailSubmit(fakeEvent());
    });
    expect(result.current.step).toBe('code');

    act(() => {
      result.current.setCode('123456');
    });
    await act(async () => {
      await result.current.handleCodeSubmit(fakeEvent());
    });

    expect(verifyPhoneAuthCode).toHaveBeenCalledWith('2025550123', '123456', '1-US');
    expect(mockFetchRegistrationOptions).toHaveBeenCalledTimes(2);
  });

  it('surfaces code-submit errors', async () => {
    verifyEmailAuthCode.mockRejectedValue({response: {data: {code: ['Expired.']}}});

    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('email'));

    act(() => {
      result.current.setEmail('ada@example.com');
    });
    await act(async () => {
      await result.current.handleEmailSubmit(fakeEvent());
    });
    act(() => {
      result.current.setCode('123456');
    });
    await act(async () => {
      await result.current.handleCodeSubmit(fakeEvent());
    });

    expect(result.current.error).toBe('Expired.');
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
