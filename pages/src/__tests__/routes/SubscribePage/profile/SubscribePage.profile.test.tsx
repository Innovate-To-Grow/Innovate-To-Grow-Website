import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
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
});
