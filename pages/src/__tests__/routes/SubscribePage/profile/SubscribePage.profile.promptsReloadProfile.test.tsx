import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SubscribePage} from '@/routes/SubscribePage/SubscribePage';
import {emailSignIn, phoneSignIn, profileData} from '@/__tests__/routes/SubscribePage/fixtures/subscribePageFixtures';

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

describe('SubscribePage — the profile step', () => {
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
    baseAuth.verifyEmailAuthCode.mockReset().mockResolvedValue(emailSignIn());
    baseAuth.requestPhoneAuthCode.mockReset().mockResolvedValue({message: 'ok'});
    baseAuth.verifyPhoneAuthCode.mockReset().mockResolvedValue(phoneSignIn());

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
});
