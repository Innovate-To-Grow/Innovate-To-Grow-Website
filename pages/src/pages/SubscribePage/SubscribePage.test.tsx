import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {SubscribePage} from './SubscribePage';

const mockUseAuth = vi.fn();
const mockUpdateProfileFields = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../../components/Auth', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../../services/auth', async () => {
  const actual = await vi.importActual<typeof import('../../services/auth')>('../../services/auth');
  return {
    ...actual,
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

describe('SubscribePage', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUpdateProfileFields.mockReset();
    mockNavigate.mockReset();

    mockUseAuth.mockReturnValue({
      user: {email: 'member@example.com'},
      isAuthenticated: true,
      register: vi.fn(),
      error: null,
      isLoading: false,
      clearError: vi.fn(),
    });
    mockUpdateProfileFields.mockResolvedValue({email: 'member@example.com'});
  });

  it('shows only the signed-in email and subscribes it', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    expect(screen.getByDisplayValue('member@example.com')).toBeDisabled();

    fireEvent.click(screen.getByRole('button', {name: 'Subscribe'}));

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({
        email_subscribe: true,
      });
    });

    expect(await screen.findByText("You're Subscribed!")).toBeInTheDocument();
    expect(screen.getByText(/member@example\.com/)).toBeInTheDocument();
  });

  it('uses the standard registration flow for signed-out users', async () => {
    const register = vi.fn().mockResolvedValue({message: 'ok', next_step: 'verify_code'});
    const clearError = vi.fn();

    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      register,
      error: null,
      isLoading: false,
      clearError,
    });

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: 'Ada'}});
    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: 'Lovelace'}});
    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'ada@example.com'}});
    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'password123'}});
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'password123'}});

    fireEvent.click(screen.getByRole('button', {name: 'Create Account and Continue'}));

    await waitFor(() => {
      expect(register).toHaveBeenCalledWith(
        'ada@example.com',
        'password123',
        'password123',
        'Ada',
        'Lovelace',
        'Personal',
      );
    });

    expect(mockNavigate).toHaveBeenCalledWith(
      '/verify-email?flow=register&email=ada%40example.com&returnTo=%2Fsubscribe',
      {replace: true},
    );
  });
});
