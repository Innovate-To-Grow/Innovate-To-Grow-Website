import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {CompleteProfilePage} from '../CompleteProfilePage';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();
const mockGetProfile = vi.fn();
const mockUpdateProfileFields = vi.fn();
const mockGetStoredSession = vi.fn();
const mockIsCurrentSession = vi.fn();

vi.mock('../../AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/features/auth/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth/api')>('@/features/auth/api');
  return {
    ...actual,
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
    getStoredSession: () => mockGetStoredSession(),
    isCurrentSession: (...args: unknown[]) => mockIsCurrentSession(...args),
    updateProfileFields: (...args: unknown[]) => mockUpdateProfileFields(...args),
  };
});

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('CompleteProfilePage', () => {
  const clearProfileCompletionRequirement = vi.fn();

  afterEach(cleanup);

  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockGetProfile.mockReset();
    mockUpdateProfileFields.mockReset();
    mockGetStoredSession.mockReset();
    mockIsCurrentSession.mockReset();
    clearProfileCompletionRequirement.mockReset();
    clearProfileCompletionRequirement.mockReturnValue(true);
    mockGetStoredSession.mockReturnValue({
      generation: 'generation-a',
      refresh: 'refresh-a',
    });
    mockIsCurrentSession.mockReturnValue(true);

    mockUseAuth.mockReturnValue({
      user: {member_uuid: 'member-a', email: 'a@example.com'},
      isAuthenticated: true,
      requiresProfileCompletion: true,
      clearProfileCompletionRequirement,
    });

    mockGetProfile.mockResolvedValue({
      first_name: '',
      middle_name: '',
      last_name: '',
      organization: '',
      title: '',
    });

    mockUpdateProfileFields.mockResolvedValue({
      first_name: 'Ada',
      middle_name: '',
      last_name: 'Lovelace',
      organization: 'Acme Corp',
      title: '',
    });
  });

  it('returns to the requested page after saving a complete profile', async () => {
    render(
      <MemoryRouter initialEntries={['/complete-profile?returnTo=%2Fevent-registration']}>
        <Routes>
          <Route path="/complete-profile" element={<CompleteProfilePage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByLabelText('First Name');

    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: 'Ada'}});
    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: 'Lovelace'}});
    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {target: {value: 'Acme Corp'}});
    fireEvent.submit(screen.getByRole('button', {name: 'Continue to Account'}).closest('form')!);

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({
        first_name: 'Ada',
        middle_name: '',
        last_name: 'Lovelace',
        organization: 'Acme Corp',
        title: '',
      });
    });

    expect(clearProfileCompletionRequirement).toHaveBeenCalledWith({
      generation: 'generation-a',
      refresh: 'refresh-a',
    });
    expect(mockNavigate).toHaveBeenCalledWith('/event-registration', {replace: true});
  });

  it('does not clear or navigate a replacement account after an in-flight save', async () => {
    let resolveSave!: (value: object) => void;
    mockUpdateProfileFields.mockReturnValue(
      new Promise((resolve) => {
        resolveSave = resolve;
      }),
    );
    clearProfileCompletionRequirement.mockReturnValue(false);

    render(
      <MemoryRouter initialEntries={['/complete-profile']}>
        <Routes>
          <Route path="/complete-profile" element={<CompleteProfilePage />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByLabelText('First Name');
    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: 'Ada'}});
    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: 'Lovelace'}});
    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {
      target: {value: 'Acme Corp'},
    });
    fireEvent.submit(screen.getByRole('button', {name: 'Continue to Account'}).closest('form')!);

    resolveSave({
      first_name: 'Ada',
      last_name: 'Lovelace',
      organization: 'Acme Corp',
    });

    await waitFor(() => {
      expect(clearProfileCompletionRequirement).toHaveBeenCalledWith({
        generation: 'generation-a',
        refresh: 'refresh-a',
      });
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('discards a stale profile response after the stored account changes', async () => {
    let resolveFirstProfile!: (value: object) => void;
    mockGetProfile
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirstProfile = resolve;
        }),
      )
      .mockResolvedValueOnce({
        first_name: 'Grace',
        middle_name: '',
        last_name: 'Hopper',
        organization: 'Navy',
        title: '',
      });

    const view = render(
      <MemoryRouter initialEntries={['/complete-profile']}>
        <Routes>
          <Route path="/complete-profile" element={<CompleteProfilePage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(mockGetProfile).toHaveBeenCalledTimes(1);
    });

    mockGetStoredSession.mockReturnValue({
      generation: 'generation-b',
      refresh: 'refresh-b',
    });
    mockUseAuth.mockReturnValue({
      user: {member_uuid: 'member-b', email: 'b@example.com'},
      isAuthenticated: true,
      requiresProfileCompletion: true,
      clearProfileCompletionRequirement,
    });
    view.rerender(
      <MemoryRouter initialEntries={['/complete-profile']}>
        <Routes>
          <Route path="/complete-profile" element={<CompleteProfilePage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByDisplayValue('Grace');
    resolveFirstProfile({
      first_name: 'Ada',
      middle_name: '',
      last_name: 'Lovelace',
      organization: 'Analytical Engines',
      title: '',
    });

    await waitFor(() => {
      expect(screen.getByLabelText('First Name')).toHaveValue('Grace');
      expect(screen.getByLabelText('Last Name')).toHaveValue('Hopper');
    });
    expect(screen.queryByDisplayValue('Ada')).not.toBeInTheDocument();
  });
});
