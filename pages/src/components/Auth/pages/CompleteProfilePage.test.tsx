import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {CompleteProfilePage} from './CompleteProfilePage';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();
const mockGetProfile = vi.fn();
const mockUpdateProfileFields = vi.fn();

vi.mock('../AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../../../services/auth', async () => {
  const actual = await vi.importActual<typeof import('../../../services/auth')>('../../../services/auth');
  return {
    ...actual,
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
    updateProfileFields: (...args: unknown[]) => mockUpdateProfileFields(...args),
  };
});

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('CompleteProfilePage', () => {
  const clearProfileCompletionRequirement = vi.fn();

  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockGetProfile.mockReset();
    mockUpdateProfileFields.mockReset();
    clearProfileCompletionRequirement.mockReset();

    mockUseAuth.mockReturnValue({
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

    expect(clearProfileCompletionRequirement).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/event-registration', {replace: true});
  });
});
