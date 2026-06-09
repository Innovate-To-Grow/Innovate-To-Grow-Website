import {act, renderHook, waitFor} from '@testing-library/react';
import type {FormEvent} from 'react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {useEventRegistration} from '@/routes/EventRegistrationPage/useEventRegistration';
import type {EventRegistrationOptions, Registration} from '@/features/events/api';

const registrationMocks = vi.hoisted(() => ({
  createRegistration: vi.fn(),
  fetchRegistrationOptions: vi.fn(),
  navigate: vi.fn(),
  requestEmailAuthCode: vi.fn(),
  sendPhoneCode: vi.fn(),
  updateProfileFields: vi.fn(),
  useAuthValue: {
    isAuthenticated: true,
    requiresProfileCompletion: false,
    requestEmailAuthCode: vi.fn(),
    verifyEmailAuthCode: vi.fn(),
  },
  verifyEmailAuthCode: vi.fn(),
  verifyPhoneCode: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => registrationMocks.navigate,
  };
});

vi.mock('@/features/auth', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth')>('@/features/auth');
  return {
    ...actual,
    updateProfileFields: registrationMocks.updateProfileFields,
    useAuth: () => registrationMocks.useAuthValue,
  };
});

vi.mock('@/features/events/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/events/api')>('@/features/events/api');
  return {
    ...actual,
    createRegistration: registrationMocks.createRegistration,
    fetchRegistrationOptions: registrationMocks.fetchRegistrationOptions,
    sendPhoneCode: registrationMocks.sendPhoneCode,
    verifyPhoneCode: registrationMocks.verifyPhoneCode,
  };
});

const submitEvent = () => ({preventDefault: vi.fn()} as unknown as FormEvent);

const registration: Registration = {
  id: 'reg-1',
  ticket_code: 'I2G-123',
  attendee_first_name: 'Ada',
  attendee_last_name: 'Lovelace',
  attendee_name: 'Ada Lovelace',
  attendee_email: 'ada@example.com',
  attendee_secondary_email: 'ada.secondary@example.com',
  attendee_phone: '+15551234567',
  phone_verified: true,
  phone_verification_required: false,
  attendee_organization: 'UC Merced',
  registered_at: '2026-06-08T00:00:00Z',
  ticket_email_sent_at: null,
  ticket_email_error: '',
  barcode_format: 'png',
  barcode_image: 'data:image/png;base64,abc',
  event: {
    id: 'event-1',
    name: 'Demo Day',
    slug: 'demo-day',
    date: '2026-05-01',
    location: 'Campus',
    description: 'Event description',
  },
  ticket: {
    id: 'ticket-1',
    name: 'General Admission',
  },
  answers: [],
};

const options = (overrides: Partial<EventRegistrationOptions> = {}): EventRegistrationOptions => ({
  id: 'event-1',
  name: 'Demo Day',
  slug: 'demo-day',
  date: '2026-05-01',
  location: 'Campus',
  description: 'Event description',
  allow_secondary_email: true,
  collect_phone: true,
  verify_phone: true,
  tickets: [{id: 'ticket-1', name: 'General Admission'}],
  questions: [{id: 'q1', text: 'Dietary restrictions?', is_required: false, order: 1}],
  registration: null,
  member_emails: ['ada@example.com', 'ada.secondary@example.com'],
  member_profile: {
    first_name: 'Ada',
    middle_name: '',
    last_name: 'Lovelace',
    organization: 'UC Merced',
    title: 'Engineer',
  },
  member_phone: {
    phone_number: '+15551234567',
    region: '1-US',
    verified: false,
  },
  phone_regions: [{code: '1-US', label: 'United States'}],
  ...overrides,
});

describe('useEventRegistration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    registrationMocks.requestEmailAuthCode.mockResolvedValue({message: 'sent'});
    registrationMocks.verifyEmailAuthCode.mockResolvedValue({next_step: 'done'});
    registrationMocks.useAuthValue = {
      isAuthenticated: true,
      requiresProfileCompletion: false,
      requestEmailAuthCode: registrationMocks.requestEmailAuthCode,
      verifyEmailAuthCode: registrationMocks.verifyEmailAuthCode,
    };
    registrationMocks.fetchRegistrationOptions.mockResolvedValue(options());
    registrationMocks.createRegistration.mockResolvedValue(registration);
    registrationMocks.sendPhoneCode.mockResolvedValue({detail: 'sent', phone: '+15551234567'});
    registrationMocks.verifyPhoneCode.mockResolvedValue({detail: 'verified', verified: true, phone: '+15551234567'});
    registrationMocks.updateProfileFields.mockResolvedValue({});
  });

  it('prefills authenticated member data, verifies phone, syncs changed profile fields, and submits registration', async () => {
    const {result} = renderHook(() => useEventRegistration());

    await waitFor(() => expect(result.current.step).toBe('form'));
    expect(result.current.primaryEmail).toBe('ada@example.com');
    expect(result.current.attendeeSecondaryEmail).toBe('ada.secondary@example.com');
    expect(result.current.attendeePhone).toBe('5551234567');
    expect(result.current.attendeeOrganization).toBe('UC Merced');

    await act(async () => {
      result.current.setSelectedTicketId('ticket-1');
      result.current.setAnswers({q1: 'Vegetarian'});
      result.current.setAttendeeTitle('Senior Engineer');
    });

    await act(async () => {
      await result.current.handleSendPhoneCode();
    });
    expect(result.current.phoneCodeSent).toBe(true);
    expect(result.current.phoneError).toBeNull();

    await act(async () => {
      result.current.setPhoneCode('123456');
    });
    await act(async () => {
      await result.current.handleVerifyPhoneCode();
    });
    expect(result.current.phoneVerified).toBe(true);

    await act(async () => {
      await result.current.handleRegistrationSubmit(submitEvent());
    });

    await waitFor(() => expect(result.current.step).toBe('done'));
    expect(registrationMocks.updateProfileFields).toHaveBeenCalledWith({
      first_name: 'Ada',
      middle_name: '',
      last_name: 'Lovelace',
      organization: 'UC Merced',
      title: 'Senior Engineer',
    });
    expect(registrationMocks.createRegistration).toHaveBeenCalledWith({
      event_slug: 'demo-day',
      ticket_id: 'ticket-1',
      attendee_first_name: 'Ada',
      attendee_last_name: 'Lovelace',
      attendee_organization: 'UC Merced',
      answers: [{question_id: 'q1', answer: 'Vegetarian'}],
      attendee_secondary_email: 'ada.secondary@example.com',
      attendee_phone: '5551234567',
      attendee_phone_region: '1-US',
    });
    expect(result.current.registration).toBe(registration);
  });

  it('routes existing registrations directly to done and redirects incomplete profiles', async () => {
    registrationMocks.fetchRegistrationOptions.mockResolvedValueOnce(options({registration}));
    const done = renderHook(() => useEventRegistration());

    await waitFor(() => expect(done.result.current.step).toBe('done'));
    expect(done.result.current.registration).toBe(registration);

    done.unmount();
    registrationMocks.fetchRegistrationOptions.mockResolvedValueOnce(options({
      member_profile: {
        first_name: '',
        middle_name: '',
        last_name: 'Lovelace',
        organization: 'UC Merced',
        title: '',
      },
    }));
    renderHook(() => useEventRegistration());

    await waitFor(() => {
      expect(registrationMocks.navigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fevent-registration', {replace: true});
    });
  });

  it('handles unauthenticated email/code flows and API errors', async () => {
    registrationMocks.useAuthValue = {
      isAuthenticated: false,
      requiresProfileCompletion: false,
      requestEmailAuthCode: registrationMocks.requestEmailAuthCode,
      verifyEmailAuthCode: registrationMocks.verifyEmailAuthCode,
    };
    registrationMocks.verifyEmailAuthCode.mockResolvedValue({
      next_step: 'complete_profile',
      requires_profile_completion: true,
    });

    const {result} = renderHook(() => useEventRegistration());

    await waitFor(() => expect(result.current.step).toBe('email'));
    await act(async () => {
      result.current.setEmail('ada@example.com');
    });
    await act(async () => {
      await result.current.handleEmailSubmit(submitEvent());
    });
    expect(result.current.step).toBe('code');

    await act(async () => {
      result.current.setCode('123456');
    });
    await act(async () => {
      await result.current.handleCodeSubmit(submitEvent());
    });

    expect(registrationMocks.navigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fevent-registration', {replace: true});
  });

  it('surfaces authenticated bootstrap failures and registration conflicts', async () => {
    registrationMocks.fetchRegistrationOptions.mockRejectedValueOnce({
      response: {data: {detail: 'No live event is currently active.'}},
    });
    const failed = renderHook(() => useEventRegistration());

    await waitFor(() => expect(failed.result.current.error).toBe('No event is currently accepting registrations.'));
    expect(failed.result.current.step).toBe('loading');
    failed.unmount();

    registrationMocks.fetchRegistrationOptions.mockResolvedValueOnce(options());
    registrationMocks.createRegistration.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {registration},
      },
    });
    const conflict = renderHook(() => useEventRegistration());

    await waitFor(() => expect(conflict.result.current.step).toBe('form'));
    await act(async () => {
      conflict.result.current.setSelectedTicketId('ticket-1');
    });
    await act(async () => {
      await conflict.result.current.handleRegistrationSubmit(submitEvent());
    });

    expect(conflict.result.current.step).toBe('done');
    expect(conflict.result.current.registration).toBe(registration);
  });
});
