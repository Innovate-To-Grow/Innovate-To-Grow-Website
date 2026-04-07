import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {SubscribePage} from './SubscribePage';

const mockUseAuth = vi.fn();
const mockGetProfile = vi.fn();
const mockUpdateProfileFields = vi.fn();

vi.mock('../../components/Auth', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../../services/auth', () => ({
  getProfile: (...args: unknown[]) => mockGetProfile(...args),
  updateProfileFields: (...args: unknown[]) => mockUpdateProfileFields(...args),
}));

describe('SubscribePage', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockGetProfile.mockReset();
    mockUpdateProfileFields.mockReset();

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      requestEmailAuthCode: vi.fn(),
      verifyEmailAuthCode: vi.fn(),
      clearProfileCompletionRequirement: vi.fn(),
    });
    mockGetProfile.mockResolvedValue({
      email: 'member@example.com',
      first_name: 'Ada',
      middle_name: 'M',
      last_name: 'Lovelace',
      organization: 'Analytical Engine',
    });
    mockUpdateProfileFields.mockResolvedValue({});
  });

  it('preloads the authenticated profile before subscribing', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Loading your profile...')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByDisplayValue('Ada')).toBeInTheDocument());
    expect(screen.getByDisplayValue('M')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Lovelace')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Analytical Engine')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Subscribe'}));

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({
        first_name: 'Ada',
        middle_name: 'M',
        last_name: 'Lovelace',
        organization: 'Analytical Engine',
        email_subscribe: true,
      });
    });
  });
});
