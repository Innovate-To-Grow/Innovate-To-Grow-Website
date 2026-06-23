import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {VerifyPhonePage} from '../VerifyPhonePage';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../../AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/verify-phone" element={<VerifyPhonePage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('VerifyPhonePage', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      requiresProfileCompletion: false,
      error: null,
      isLoading: false,
      verifyPhoneAuthCode: vi.fn(),
      requestPhoneAuthCode: vi.fn(),
      clearError: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('verifies the code and routes new accounts to complete-profile', async () => {
    renderAt('/verify-phone?phone=2025550123');
    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyPhoneAuthCode.mockResolvedValue({next_step: 'complete_profile', requires_profile_completion: true});

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '654321'}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify'}));

    await waitFor(() => {
      expect(authValue.verifyPhoneAuthCode).toHaveBeenCalledWith('2025550123', '654321');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/complete-profile', {replace: true});
  });

  it('routes a returning account to a safe returnTo', async () => {
    renderAt('/verify-phone?phone=2025550123&returnTo=%2Fpast-projects');
    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyPhoneAuthCode.mockResolvedValue({next_step: 'account', requires_profile_completion: false});

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '654321'}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify'}));

    await waitFor(() => {
      expect(authValue.verifyPhoneAuthCode).toHaveBeenCalled();
    });
    expect(mockNavigate).toHaveBeenCalledWith('/past-projects', {replace: true});
  });

  it('resends the code through the phone-auth endpoint', async () => {
    renderAt('/verify-phone?phone=2025550123');
    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestPhoneAuthCode.mockResolvedValue({message: 'Code resent.'});

    const resendButtons = screen.getAllByRole('button', {name: 'Resend code'});
    fireEvent.click(resendButtons.at(-1)!);

    await waitFor(() => {
      expect(authValue.requestPhoneAuthCode).toHaveBeenCalledWith('2025550123', '1-US', 'login');
    });
    expect(await screen.findByText('Code resent.')).toBeInTheDocument();
  });

  it('redirects to /login when the phone param is not a valid US number', () => {
    renderAt('/verify-phone?phone=123');
    expect(screen.queryByRole('button', {name: 'Verify'})).not.toBeInTheDocument();
  });

  it('stays on the verify screen when verification fails', async () => {
    renderAt('/verify-phone?phone=2025550123');
    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.verifyPhoneAuthCode.mockRejectedValue(new Error('invalid code'));

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '000000'}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify'}));

    await waitFor(() => {
      expect(authValue.verifyPhoneAuthCode).toHaveBeenCalled();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
