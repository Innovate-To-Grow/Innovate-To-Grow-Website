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

describe('SubscribePage', () => {
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

  it('shows email step for unauthenticated users', () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText('Email or Phone')).toBeInTheDocument();
  });

  it('transitions from email to code step on submit', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

    await waitFor(() => {
      expect(baseAuth.requestEmailAuthCode).toHaveBeenCalledWith('test@example.com', 'subscribe');
    });

    expect(await screen.findByLabelText('Verification Code')).toBeInTheDocument();
  });

  it('routes a phone entry to the SMS-code flow with the subscribe source', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: '(202) 555-0123'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

    await waitFor(() => {
      expect(baseAuth.requestPhoneAuthCode).toHaveBeenCalledWith('2025550123', '1-US', 'subscribe');
    });
    expect(baseAuth.requestEmailAuthCode).not.toHaveBeenCalled();
  });

  it('transitions from code to profile step when profile is incomplete', async () => {
    const authState = {
      ...baseAuth,
      user: null as {member_uuid: string; email: string} | null,
      isAuthenticated: false,
      verifyEmailAuthCode: vi.fn().mockImplementation(async () => {
        authState.user = {member_uuid: 'uuid-1', email: 'test@example.com'};
        authState.isAuthenticated = true;
        return {
          access: 'jwt',
          refresh: 'jwt-r',
          user: authState.user,
          requires_profile_completion: true,
        };
      }),
    };
    mockUseAuth.mockImplementation(() => authState);

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    // Go to code step
    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);
    await screen.findByLabelText('Verification Code');

    // Submit code
    fireEvent.change(screen.getByLabelText('Verification Code'), {target: {value: '123456'}});
    fireEvent.submit(screen.getByLabelText('Verification Code').closest('form')!);

    await waitFor(() => {
      expect(authState.verifyEmailAuthCode).toHaveBeenCalledWith('test@example.com', '123456');
    });

    await waitFor(() => {
      expect(mockGetProfile).toHaveBeenCalled();
    });

    expect(await screen.findByLabelText(/first name/i)).toBeInTheDocument();
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
    expect(screen.queryByRole('button', {name: 'Turn on newsletter subscription'})).not.toBeInTheDocument();
  });

  it('opens directly on the profile step when the query requests it', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });

    mockGetProfile.mockResolvedValue({
      ...profileData,
      organization: 'Acme Corp',
      title: 'Director',
    });

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockGetProfile).toHaveBeenCalled();
      expect(screen.getAllByLabelText(/first name/i).some((input) => (input as HTMLInputElement).value === 'Ada')).toBe(true);
      expect(screen.getAllByLabelText(/last name/i).some((input) => (input as HTMLInputElement).value === 'Lovelace')).toBe(true);
      expect(
        screen.getAllByPlaceholderText('Company or organization name').some(
          (input) => (input as HTMLInputElement).value === 'Acme Corp',
        ),
      ).toBe(true);
      expect(
        screen.getAllByPlaceholderText('Your title or position (e.g. CEO, Director)').some(
          (input) => (input as HTMLInputElement).value === 'Director',
        ),
      ).toBe(true);
    });
  });

  it('preserves prefilled profile data from the direct link and advances to manage after save', async () => {
    const incompleteProfile = {
      ...profileData,
      last_name: '',
      organization: 'Acme Corp',
      title: 'Director',
    };
    const completedProfile = {
      ...incompleteProfile,
      last_name: 'Lovelace',
      email_subscribe: true,
    };

    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile
      .mockResolvedValueOnce(incompleteProfile)
      .mockResolvedValue(completedProfile);
    mockUpdateProfileFields.mockResolvedValue(completedProfile);

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    const activeFirstNameInput = await screen.findByLabelText(/first name/i);
    const activeLastNameInput = screen.getByLabelText(/last name/i);
    const activeOrgInput = screen.getByPlaceholderText('Company or organization name');
    const activeTitleInput = screen.getByPlaceholderText('Your title or position (e.g. CEO, Director)');

    expect(activeFirstNameInput).toHaveValue('Ada');
    expect(activeOrgInput).toHaveValue('Acme Corp');
    expect(activeTitleInput).toHaveValue('Director');

    fireEvent.change(activeLastNameInput, {target: {value: 'Lovelace'}});
    fireEvent.submit(activeFirstNameInput.closest('form')!);

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({
        first_name: 'Ada',
        middle_name: '',
        last_name: 'Lovelace',
        organization: 'Acme Corp',
        title: 'Director',
        email_subscribe: true,
      });
    });

    expect(await screen.findByText('Manage your email and text message subscription preferences below.')).toBeInTheDocument();
    expect(baseAuth.clearProfileCompletionRequirement).toHaveBeenCalledWith({
      generation: 'generation-a',
    });
  });

  it('does not apply an in-flight profile save to a replacement account', async () => {
    const incompleteProfile = {
      ...profileData,
      last_name: '',
      organization: 'Acme Corp',
    };
    let resolveSave!: (value: typeof profileData) => void;
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockResolvedValue(incompleteProfile);
    mockUpdateProfileFields.mockReturnValue(
      new Promise((resolve) => {
        resolveSave = resolve;
      }),
    );
    baseAuth.clearProfileCompletionRequirement.mockReturnValue(false);

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    const firstName = await screen.findByLabelText(/first name/i);
    fireEvent.change(screen.getByLabelText(/last name/i), {
      target: {value: 'Lovelace'},
    });
    fireEvent.submit(firstName.closest('form')!);

    resolveSave({...profileData, organization: 'Acme Corp'});

    await waitFor(() =>
      expect(baseAuth.clearProfileCompletionRequirement).toHaveBeenCalledWith({
        generation: 'generation-a',
      }),
    );
    expect(
      screen.queryByText(
        'Manage your email and text message subscription preferences below.',
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
  });

  it('does not apply an incomplete stale profile response after an account switch', async () => {
    const incompleteProfile = {
      ...profileData,
      last_name: '',
      organization: 'Acme Corp',
    };
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockResolvedValue(incompleteProfile);
    mockUpdateProfileFields.mockResolvedValue(incompleteProfile);
    mockIsCurrentSession.mockReturnValue(false);

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    const firstName = await screen.findByLabelText(/first name/i);
    fireEvent.submit(firstName.closest('form')!);

    await waitFor(() =>
      expect(mockIsCurrentSession).toHaveBeenCalledWith({
        generation: 'generation-a',
      }),
    );
    expect(baseAuth.clearProfileCompletionRequirement).not.toHaveBeenCalled();
    expect(
      screen.queryByText(
        'Manage your email and text message subscription preferences below.',
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
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
    const toggleButtons = await screen.findAllByRole('button', {name: 'Turn off newsletter subscription'});
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
    expect(await screen.findByText('(415)555-0132')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Turn on newsletter subscription for secondary@example.com'}));
    await waitFor(() => {
      expect(mockUpdateContactEmail).toHaveBeenCalledWith('email-2', {subscribe: true});
    });

    fireEvent.click(screen.getByRole('button', {name: 'Turn off text messages for (415)555-0132'}));
    await waitFor(() => {
      expect(mockUpdateContactPhone).toHaveBeenCalledWith('phone-1', {subscribe: false});
    });
  });

  it('saves profile and auto-subscribes in profile step', async () => {
    const authState = {
      ...baseAuth,
      user: null as {member_uuid: string; email: string} | null,
      isAuthenticated: false,
      verifyEmailAuthCode: vi.fn().mockImplementation(async () => {
        authState.user = {member_uuid: 'uuid-1', email: 'test@example.com'};
        authState.isAuthenticated = true;
        return {
          access: 'jwt',
          refresh: 'jwt-r',
          user: authState.user,
          requires_profile_completion: true,
        };
      }),
    };
    mockUseAuth.mockImplementation(() => authState);

    mockUpdateProfileFields.mockResolvedValue({
      ...profileData,
      email: 'test@example.com',
      organization: 'Acme Corp',
      title: '',
      email_subscribe: true,
    });
    mockGetProfile.mockResolvedValue({
      ...profileData,
      email: 'test@example.com',
      organization: '',
      title: '',
      email_subscribe: true,
    });

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    // Navigate to code step
    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);
    await screen.findByLabelText('Verification Code');

    // Verify code → profile step
    fireEvent.change(screen.getByLabelText('Verification Code'), {target: {value: '123456'}});
    fireEvent.submit(screen.getByLabelText('Verification Code').closest('form')!);
    await waitFor(() => {
      expect(authState.verifyEmailAuthCode).toHaveBeenCalledWith('test@example.com', '123456');
      expect(mockGetProfile).toHaveBeenCalled();
    });

    const firstNameInput = await screen.findByLabelText(/first name/i);
    const lastNameInput = screen.getByLabelText(/last name/i);
    const orgInput = screen.getByPlaceholderText('Company or organization name');

    fireEvent.change(firstNameInput, {target: {value: 'Ada'}});
    fireEvent.change(lastNameInput, {target: {value: 'Lovelace'}});
    fireEvent.change(orgInput, {target: {value: 'Acme Corp'}});
    fireEvent.submit(firstNameInput.closest('form')!);

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({
        first_name: 'Ada',
        middle_name: '',
        last_name: 'Lovelace',
        organization: 'Acme Corp',
        title: '',
        email_subscribe: true,
      });
    });

    expect(baseAuth.clearProfileCompletionRequirement).toHaveBeenCalledWith({
      generation: 'generation-a',
    });
  });

  it('shows an error for an invalid email or phone entry', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'not-an-email'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

    expect(
      await screen.findByText('Please enter a valid email address or 10-digit US phone number.'),
    ).toBeInTheDocument();
    expect(baseAuth.requestEmailAuthCode).not.toHaveBeenCalled();
    expect(baseAuth.requestPhoneAuthCode).not.toHaveBeenCalled();
  });

  it('surfaces an auth-code error from the email submit', async () => {
    baseAuth.requestEmailAuthCode.mockRejectedValueOnce({response: {data: {detail: 'Rate limited.'}}});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

    expect(await screen.findByText('Rate limited.')).toBeInTheDocument();
  });

  it('lands on manage when the verified account already has a complete profile', async () => {
    baseAuth.verifyEmailAuthCode.mockResolvedValueOnce({
      access: 'jwt',
      refresh: 'jwt-r',
      user: {member_uuid: 'uuid-1', email: 'test@example.com'},
      requires_profile_completion: false,
    });

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);
    const codeInput = await screen.findByLabelText('Verification Code');
    fireEvent.change(codeInput, {target: {value: '123456'}});
    fireEvent.submit(codeInput.closest('form')!);

    expect(
      await screen.findByText('Manage your email and text message subscription preferences below.'),
    ).toBeInTheDocument();
  });

  it('shows a verify error from the code submit', async () => {
    baseAuth.verifyEmailAuthCode.mockRejectedValueOnce({response: {data: {code: ['Expired.']}}});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);
    const codeInput = await screen.findByLabelText('Verification Code');
    fireEvent.change(codeInput, {target: {value: '123456'}});
    fireEvent.submit(codeInput.closest('form')!);

    expect(await screen.findByText('Expired.')).toBeInTheDocument();
  });

  it('resends the email code and surfaces resend errors', async () => {
    vi.useFakeTimers();
    try {
      baseAuth.requestEmailAuthCode
        .mockResolvedValueOnce({message: 'ok'})
        .mockRejectedValueOnce({response: {data: {detail: 'Too many codes.'}}});

      render(
        <MemoryRouter>
          <SubscribePage />
        </MemoryRouter>,
      );

      fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
      fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByLabelText('Verification Code')).toBeInTheDocument();

      for (let i = 0; i < 30; i += 1) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1000);
        });
      }

      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

      await act(async () => {
        await Promise.resolve();
      });

      expect(screen.getByText('Too many codes.')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('returns to the email step from the code step', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);
    await screen.findByLabelText('Verification Code');

    fireEvent.click(screen.getByRole('button', {name: 'Use a different email or phone'}));

    expect(screen.getByLabelText('Email or Phone')).toBeInTheDocument();
  });

  it('prompts to reload when the profile fetch fails and retries', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockRejectedValueOnce(new Error('network down'));

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Failed to load your profile.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Retry'}));

    expect(await screen.findByLabelText(/first name/i)).toBeInTheDocument();
    expect(mockGetProfile).toHaveBeenCalledTimes(2);
  });

  it('warns when the profile session changed mid-save', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockResolvedValue(profileData);
    mockGetStoredSession.mockReturnValue(null);

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    const firstName = await screen.findByLabelText(/first name/i);
    fireEvent.submit(firstName.closest('form')!);

    expect(
      await screen.findByText('Your session changed. Reload the page and try again.'),
    ).toBeInTheDocument();
    expect(mockUpdateProfileFields).not.toHaveBeenCalled();
  });

  it('surfaces profile save errors', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockResolvedValue(profileData);
    mockUpdateProfileFields.mockRejectedValueOnce({response: {data: {detail: 'Save failed.'}}});

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    const firstName = await screen.findByLabelText(/first name/i);
    fireEvent.submit(firstName.closest('form')!);

    expect(await screen.findByText('Save failed.')).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('button', {name: 'Turn off newsletter subscription'}));

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
      screen.getByRole('button', {name: 'Turn on newsletter subscription for secondary@example.com'}),
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

    await screen.findByText('(415)555-0132');
    fireEvent.click(
      screen.getByRole('button', {name: 'Turn off text messages for (415)555-0132'}),
    );

    expect(await screen.findByText('Phone toggle failed.')).toBeInTheDocument();
  });

  it('updates profile fields through the profile step inputs', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockResolvedValue(profileData);

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    await screen.findByLabelText(/first name/i);
    fireEvent.change(screen.getByLabelText(/first name/i), {target: {value: 'Grace'}});
    fireEvent.change(screen.getByLabelText(/middle name/i), {target: {value: 'Hopper'}});
    fireEvent.click(screen.getByRole('button', {name: 'Organization'}));
    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {target: {value: 'Navy'}});
    fireEvent.change(
      screen.getByPlaceholderText('Your title or position (e.g. CEO, Director)'),
      {target: {value: 'Admiral'}},
    );

    expect(screen.getByLabelText(/first name/i)).toHaveValue('Grace');
    expect(screen.getByLabelText(/middle name/i)).toHaveValue('Hopper');
    expect(screen.getByPlaceholderText('Company or organization name')).toHaveValue('Navy');
    expect(screen.getByPlaceholderText('Your title or position (e.g. CEO, Director)')).toHaveValue('Admiral');
  });

  it('tolerates null profile fields and treats Personal as an individual', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockResolvedValue({
      ...profileData,
      first_name: null,
      middle_name: null,
      last_name: null,
      organization: 'Personal',
      title: null,
    });

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetProfile).toHaveBeenCalled());
    expect(await screen.findByLabelText(/first name/i)).toHaveValue('');
    expect(screen.getByLabelText(/last name/i)).toHaveValue('');
    expect(screen.queryByPlaceholderText('Company or organization name')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Your title or position (e.g. CEO, Director)')).not.toBeInTheDocument();
  });

  it('advances to manage when auth completes while on the email step', async () => {
    mockUseAuth.mockReturnValue({...baseAuth});
    const {rerender} = render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText('Email or Phone')).toBeInTheDocument();

    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    rerender(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText('Manage your email and text message subscription preferences below.'),
    ).toBeInTheDocument();
  });

  it('ignores a stale profile response after unmounting', async () => {
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
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
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

  it('ignores a stale profile error after unmounting', async () => {
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
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
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

  it('resends the phone code via the SMS resend path', async () => {
    vi.useFakeTimers();
    try {
      render(
        <MemoryRouter>
          <SubscribePage />
        </MemoryRouter>,
      );

      fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: '(202) 555-0123'}});
      fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByLabelText('Verification Code')).toBeInTheDocument();

      for (let i = 0; i < 30; i += 1) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1000);
        });
      }

      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

      await act(async () => {
        await Promise.resolve();
      });

      expect(baseAuth.requestPhoneAuthCode).toHaveBeenCalledTimes(2);
      expect(baseAuth.requestPhoneAuthCode).toHaveBeenLastCalledWith('2025550123', '1-US', 'subscribe');
    } finally {
      vi.useRealTimers();
    }
  });
});
