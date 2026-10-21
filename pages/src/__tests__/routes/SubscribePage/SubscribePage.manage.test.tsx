import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SubscribePage} from '@/routes/SubscribePage/SubscribePage';

const mockUseAuth = vi.fn();
const mockGetProfile = vi.fn();
const mockGetStoredSession = vi.fn();
const mockIsCurrentSession = vi.fn();
const mockUpdateProfileFields = vi.fn();
const mockGetContactEmails = vi.fn();
const mockGetContactPhones = vi.fn();
const mockUpdateContactEmail = vi.fn();
const mockUpdateContactPhone = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
    getStoredSession: () => mockGetStoredSession(),
    isCurrentSession: (...args: unknown[]) => mockIsCurrentSession(...args),
    updateProfileFields: (...args: unknown[]) => mockUpdateProfileFields(...args),
    getContactEmails: (...args: unknown[]) => mockGetContactEmails(...args),
    getContactPhones: (...args: unknown[]) => mockGetContactPhones(...args),
    updateContactEmail: (...args: unknown[]) => mockUpdateContactEmail(...args),
    updateContactPhone: (...args: unknown[]) => mockUpdateContactPhone(...args),
  };
});

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

const baseAuth = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  clearError: vi.fn(),
  clearProfileCompletionRequirement: vi.fn(),
  requestEmailAuthCode: vi.fn().mockResolvedValue({message: 'ok'}),
  verifyEmailAuthCode: vi.fn().mockResolvedValue({
    access: 'jwt',
    refresh: 'jwt-r',
    user: {member_uuid: 'uuid-1', email: 'test@example.com'},
    requires_profile_completion: true,
  }),
  requestPhoneAuthCode: vi.fn().mockResolvedValue({message: 'ok'}),
  verifyPhoneAuthCode: vi.fn().mockResolvedValue({
    access: 'jwt',
    refresh: 'jwt-r',
    user: {member_uuid: 'uuid-1', phone: '+12025550123'},
    requires_profile_completion: false,
  }),
};

const profileData = {
  member_uuid: 'uuid-1',
  email: 'member@example.com',
  email_verified: true,
  primary_email_id: 'eid-1',
  first_name: 'Ada',
  middle_name: '',
  last_name: 'Lovelace',
  organization: 'Individual',
  title: '',
  email_subscribe: false,
  is_staff: false,
  is_active: true,
  date_joined: '2026-01-01',
};

describe('SubscribePage — managing subscriptions', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockUseAuth.mockReset();
    mockGetProfile.mockReset();
    mockGetStoredSession.mockReset();
    mockIsCurrentSession.mockReset();
    mockUpdateProfileFields.mockReset();
    mockGetContactEmails.mockReset();
    mockGetContactPhones.mockReset();
    mockUpdateContactEmail.mockReset();
    mockUpdateContactPhone.mockReset();
    baseAuth.clearError.mockReset();
    baseAuth.clearProfileCompletionRequirement.mockReset();
    baseAuth.clearProfileCompletionRequirement.mockReturnValue(true);
    baseAuth.requestEmailAuthCode.mockReset().mockResolvedValue({message: 'ok'});
    baseAuth.verifyEmailAuthCode.mockReset().mockResolvedValue({
      access: 'jwt',
      refresh: 'jwt-r',
      user: {member_uuid: 'uuid-1', email: 'test@example.com'},
      requires_profile_completion: true,
    });
    baseAuth.requestPhoneAuthCode.mockReset().mockResolvedValue({message: 'ok'});
    baseAuth.verifyPhoneAuthCode.mockReset().mockResolvedValue({
      access: 'jwt',
      refresh: 'jwt-r',
      user: {member_uuid: 'uuid-1', phone: '+12025550123'},
      requires_profile_completion: false,
    });

    mockGetProfile.mockResolvedValue(profileData);
    mockGetStoredSession.mockReturnValue({
      generation: 'generation-a',
      refresh: 'refresh-a',
    });
    mockIsCurrentSession.mockReturnValue(true);
    mockGetContactEmails.mockResolvedValue([]);
    mockGetContactPhones.mockResolvedValue([]);
    mockUseAuth.mockReturnValue({...baseAuth});
  });

  it('shows manage step directly for authenticated users', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });

    mockGetProfile.mockResolvedValue({...profileData, email_subscribe: true});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockGetProfile).toHaveBeenCalled();
    });

    // Use getAllBy since strict mode may cause multiple renders
    const emailElements = await screen.findAllByText('member@example.com');
    expect(emailElements.length).toBeGreaterThanOrEqual(1);

    const newsletterLabels = screen.getAllByText('Newsletters');
    expect(newsletterLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('shows a terminal preferences error and retries explicitly', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockRejectedValueOnce(new Error('network down'));

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText('Failed to load subscription preferences.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Loading subscription preferences...'),
    ).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: 'Retry'}));

    expect(await screen.findByText('member@example.com')).toBeInTheDocument();
    expect(mockGetProfile).toHaveBeenCalledTimes(2);
  });

  it('hides the primary newsletter row for phone-only accounts', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: ''},
      isAuthenticated: true,
    });

    mockGetProfile.mockResolvedValue({
      ...profileData,
      email: '',
      email_verified: false,
      primary_email_id: null,
      email_subscribe: false,
    });

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockGetProfile).toHaveBeenCalled();
    });

    expect(await screen.findByText('No email addresses are connected to this account.')).toBeInTheDocument();
    expect(screen.queryByText('Primary email - Unverified')).not.toBeInTheDocument();
    expect(screen.queryByRole('switch', {name: /^Newsletters for/})).not.toBeInTheDocument();
  });

  it('toggles subscription in manage step', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });

    mockGetProfile.mockResolvedValue({...profileData, email_subscribe: true});
    mockUpdateProfileFields.mockResolvedValue({...profileData, email_subscribe: false});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockGetProfile).toHaveBeenCalled();
    });

    // Wait for the toggle button to appear
    const toggleButtons = await screen.findAllByRole('switch', {name: 'Newsletters for member@example.com'});
    // The state is announced from aria-checked; the name stays the same either way.
    expect(toggleButtons[0]).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(toggleButtons[0]);

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({email_subscribe: false});
    });
  });

  it('shows all contact emails and phones in the manage step and toggles each preference', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });

    mockGetProfile.mockResolvedValue({...profileData, email_subscribe: true});
    mockGetContactEmails.mockResolvedValue([
      {
        id: 'email-2',
        email_address: 'secondary@example.com',
        email_type: 'secondary',
        subscribe: false,
        verified: true,
        created_at: '2026-01-02',
      },
    ]);
    mockGetContactPhones.mockResolvedValue([
      {
        id: 'phone-1',
        phone_number: '+14155550132',
        region: '1-US',
        region_display: 'United States',
        subscribe: true,
        verified: true,
        created_at: '2026-01-03',
      },
    ]);
    mockUpdateContactEmail.mockResolvedValue({
      id: 'email-2',
      email_address: 'secondary@example.com',
      email_type: 'secondary',
      subscribe: true,
      verified: true,
      created_at: '2026-01-02',
    });
    mockUpdateContactPhone.mockResolvedValue({
      id: 'phone-1',
      phone_number: '+14155550132',
      region: '1-US',
      region_display: 'United States',
      subscribe: false,
      verified: true,
      created_at: '2026-01-03',
    });

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('secondary@example.com')).toBeInTheDocument();
    expect(await screen.findByText('(415) 555-0132')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('switch', {name: 'Newsletters for secondary@example.com'}));
    await waitFor(() => {
      expect(mockUpdateContactEmail).toHaveBeenCalledWith('email-2', {subscribe: true});
    });

    fireEvent.click(screen.getByRole('switch', {name: 'Text messages for (415) 555-0132'}));
    await waitFor(() => {
      expect(mockUpdateContactPhone).toHaveBeenCalledWith('phone-1', {subscribe: false});
    });
  });

  it('surfaces an error when the primary email toggle fails', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockResolvedValue({...profileData, email_subscribe: true});
    mockUpdateProfileFields.mockRejectedValueOnce({response: {data: {detail: 'Toggle failed.'}}});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    await screen.findByText('member@example.com');
    fireEvent.click(screen.getByRole('switch', {name: 'Newsletters for member@example.com'}));

    expect(await screen.findByText('Toggle failed.')).toBeInTheDocument();
  });

  it('surfaces an error when a contact email toggle fails', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockResolvedValue({...profileData, email_subscribe: true});
    mockGetContactEmails.mockResolvedValue([
      {
        id: 'email-2',
        email_address: 'secondary@example.com',
        email_type: 'secondary',
        subscribe: false,
        verified: true,
        created_at: '2026-01-02',
      },
    ]);
    mockUpdateContactEmail.mockRejectedValueOnce({response: {data: {detail: 'Email toggle failed.'}}});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    await screen.findByText('secondary@example.com');
    fireEvent.click(
      screen.getByRole('switch', {name: 'Newsletters for secondary@example.com'}),
    );

    expect(await screen.findByText('Email toggle failed.')).toBeInTheDocument();
  });

  it('surfaces an error when a contact phone toggle fails', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockResolvedValue({...profileData, email_subscribe: true});
    mockGetContactPhones.mockResolvedValue([
      {
        id: 'phone-1',
        phone_number: '+14155550132',
        region: '1-US',
        region_display: 'United States',
        subscribe: true,
        verified: true,
        created_at: '2026-01-03',
      },
    ]);
    mockUpdateContactPhone.mockRejectedValueOnce({response: {data: {detail: 'Phone toggle failed.'}}});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    await screen.findByText('(415) 555-0132');
    fireEvent.click(
      screen.getByRole('switch', {name: 'Text messages for (415) 555-0132'}),
    );

    expect(await screen.findByText('Phone toggle failed.')).toBeInTheDocument();
  });

  it('ignores a stale preferences error after unmounting', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    let rejectProfile!: (reason: unknown) => void;
    mockGetProfile.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectProfile = reject;
      }),
    );

    const {unmount} = render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(mockGetProfile).toHaveBeenCalled());

    unmount();
    await act(async () => {
      rejectProfile(new Error('down'));
      await Promise.resolve();
    });

    expect(mockGetProfile).toHaveBeenCalledTimes(1);
  });

  it('ignores a stale preferences response after unmounting', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    let resolveProfile!: (value: typeof profileData) => void;
    mockGetProfile.mockReturnValue(
      new Promise((resolve) => {
        resolveProfile = resolve;
      }),
    );

    const {unmount} = render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(mockGetProfile).toHaveBeenCalled());

    unmount();
    await act(async () => {
      resolveProfile(profileData);
      await Promise.resolve();
    });

    expect(mockGetProfile).toHaveBeenCalledTimes(1);
  });
});
