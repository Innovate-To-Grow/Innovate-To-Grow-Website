import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {CompleteProfilePage} from '@/features/auth/components/pages/CompleteProfilePage';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();
const mockGetProfile = vi.fn();
const mockUpdateProfileFields = vi.fn();
const mockGetStoredSession = vi.fn();
const mockIsCurrentSession = vi.fn();

vi.mock('@/features/auth/components/AuthContext', () => ({
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

  it('surfaces a save failure', async () => {
    mockUpdateProfileFields.mockRejectedValue({response: {data: {detail: 'Save failed'}}});

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

    expect(await screen.findByText('Save failed')).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('switches to individual and submits the literal Individual organization', async () => {
    render(
      <MemoryRouter initialEntries={['/complete-profile']}>
        <Routes>
          <Route path="/complete-profile" element={<CompleteProfilePage />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByLabelText('First Name');

    fireEvent.click(screen.getByRole('button', {name: 'Individual'}));
    expect(screen.queryByPlaceholderText('Company or organization name')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: 'Ada'}});
    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: 'Lovelace'}});
    fireEvent.submit(screen.getByRole('button', {name: 'Continue to Account'}).closest('form')!);

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({
        first_name: 'Ada',
        middle_name: '',
        last_name: 'Lovelace',
        organization: 'Individual',
        title: '',
      });
    });
    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
  });
});
