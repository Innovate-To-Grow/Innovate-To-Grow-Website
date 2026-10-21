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

  it.each([
    [{collect_phone: true, require_phone: true}, 'Phone number is required.'],
    [{allow_secondary_email: true, require_secondary_email: true}, 'Secondary email is required.'],
  ] as const)('rejects required contacts before saving profile changes', async (flags, message) => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions(flags));
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));
    act(() => {
      result.current.setSelectedTicketId('ticket-1');
      result.current.setAttendeeFirstName('Grace');
    });
    await act(async () => { await result.current.handleRegistrationSubmit(fakeEvent()); });
    expect(result.current.error).toBe(message);
    expect(mockUpdateProfileFields).not.toHaveBeenCalled();
    expect(mockCreateRegistration).not.toHaveBeenCalled();
  });

  it('omits stale hidden contacts even when their dependent flags remain enabled', async () => {
    mockUseAuth.mockReturnValue({...authenticated});
    mockFetchRegistrationOptions.mockResolvedValue(formOptions({require_phone: true, verify_phone: true, require_secondary_email: true, verify_secondary_email: true}));
    const {result} = renderHook(() => useEventRegistration(), {wrapper});
    await waitFor(() => expect(result.current.step).toBe('form'));
    act(() => {
      result.current.setSelectedTicketId('ticket-1');
      result.current.handlePhoneChange('2025550123');
      result.current.handleSecondaryEmailChange('ada@example.com');
    });
    await act(async () => { await result.current.handleRegistrationSubmit(fakeEvent()); });
    expect(mockCreateRegistration).toHaveBeenCalledWith(expect.objectContaining({
      attendee_secondary_email: undefined, attendee_phone: undefined,
      phone_verification_challenge_id: undefined, secondary_email_verification_token: undefined,
    }));
  });
});
