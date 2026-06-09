import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {VerifyEmailPage} from '@/features/auth/components/pages/VerifyEmailPage';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();

vi.mock('@/features/auth/components/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('VerifyEmailPage', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();

    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      requiresProfileCompletion: false,
      error: null,
      isLoading: false,
      requestEmailAuthCode: vi.fn(),
      verifyEmailAuthCode: vi.fn(),
      clearError: vi.fn(),
      verifyLoginCode: vi.fn(),
      verifyRegistrationCode: vi.fn().mockResolvedValue({message: 'ok'}),
      resendRegistrationCode: vi.fn(),
      requestLoginCode: vi.fn(),
      requestPasswordReset: vi.fn(),
      verifyPasswordResetCode: vi.fn(),
      confirmPasswordReset: vi.fn(),
      requestPasswordChangeCode: vi.fn(),
      verifyPasswordChangeCode: vi.fn(),
      confirmPasswordChange: vi.fn(),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('redirects malformed verification links back to login', () => {
    render(
      <MemoryRouter initialEntries={['/verify-email?flow=unknown&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/login" element={<div>Login route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Login route')).toBeInTheDocument();
  });

  it('redirects anonymous password-change links back to login', () => {
    render(
      <MemoryRouter initialEntries={['/verify-email?flow=change&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/login" element={<div>Login route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Login route')).toBeInTheDocument();
  });

  it('redirects authenticated registration links to a safe return path', () => {
    mockUseAuth.mockReturnValue({
      ...mockUseAuth(),
      isAuthenticated: true,
      requiresProfileCompletion: false,
    });

    render(
      <MemoryRouter initialEntries={['/verify-email?flow=register&email=ada@example.com&returnTo=%2Fsubscribe']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/subscribe" element={<div>Subscribe route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Subscribe route')).toBeInTheDocument();
  });

  it('sends authenticated login links through profile completion when required', () => {
    mockUseAuth.mockReturnValue({
      ...mockUseAuth(),
      isAuthenticated: true,
      requiresProfileCompletion: true,
    });

    render(
      <MemoryRouter initialEntries={['/verify-email?flow=login&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/complete-profile" element={<div>Profile route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Profile route')).toBeInTheDocument();
  });

  it('verifies auth and login codes before navigating to the post-auth path', async () => {
    const authValue = {
      ...mockUseAuth(),
      verifyEmailAuthCode: vi.fn().mockResolvedValue({redirect_to: '/account'}),
      verifyLoginCode: vi.fn().mockResolvedValue({next_step: 'complete_profile', redirect_to: '/schedule'}),
    };

    mockUseAuth.mockReturnValue(authValue);

    const {unmount} = render(
      <MemoryRouter initialEntries={['/verify-email?flow=auth&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '111222'}});
    fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

    await waitFor(() => {
      expect(authValue.verifyEmailAuthCode).toHaveBeenCalledWith('ada@example.com', '111222');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});

    unmount();
    mockNavigate.mockClear();

    render(
      <MemoryRouter initialEntries={['/verify-email?flow=login&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '333444'}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));

    await waitFor(() => {
      expect(authValue.verifyLoginCode).toHaveBeenCalledWith('ada@example.com', '333444');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fschedule', {replace: true});
  });

  it('returns to /subscribe after register verification when returnTo is safe', async () => {
    render(
      <MemoryRouter initialEntries={['/verify-email?flow=register&email=ada@example.com&returnTo=%2Fsubscribe']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const authValue = mockUseAuth.mock.results.at(-1)?.value;

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '123456'}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify and Activate'}));

    await waitFor(() => {
      expect(authValue.verifyRegistrationCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/subscribe', {replace: true});
  });

  it('routes registration verification through complete-profile when the server requests it', async () => {
    mockUseAuth.mockReturnValue({
      ...mockUseAuth(),
      verifyRegistrationCode: vi
        .fn()
        .mockResolvedValue({next_step: 'complete_profile', redirect_to: '/event-registration'}),
    });

    render(
      <MemoryRouter initialEntries={['/verify-email?flow=register&email=ada@example.com&returnTo=%2Fsubscribe']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '123456'}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify and Activate'}));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fevent-registration', {replace: true});
    });
  });

  it('verifies and confirms password reset codes before returning to login', async () => {
    const authValue = {
      ...mockUseAuth(),
      verifyPasswordResetCode: vi.fn().mockResolvedValue({verification_token: 'reset-token'}),
      confirmPasswordReset: vi.fn().mockResolvedValue({message: 'Password reset.'}),
    };
    mockUseAuth.mockReturnValue(authValue);

    render(
      <MemoryRouter initialEntries={['/verify-email?flow=reset&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '654321'}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify Code'}));

    expect(await screen.findByText('Code verified. Set your new password below.')).toBeInTheDocument();
    let scheduledRedirect: TimerHandler | undefined;
    const timeoutSpy = vi.spyOn(window, 'setTimeout').mockImplementation((handler: TimerHandler) => {
      scheduledRedirect = handler;
      return 0 as unknown as number;
    });
    fireEvent.change(screen.getByLabelText('New Password'), {target: {value: 'super-secret'}});
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'super-secret'}});
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Reset Password'}));
      await Promise.resolve();
    });

    expect(authValue.confirmPasswordReset).toHaveBeenCalledWith(
      'ada@example.com',
      'reset-token',
      'super-secret',
      'super-secret',
    );
    expect(screen.getByText('Password reset.')).toBeInTheDocument();
    expect(timeoutSpy).toHaveBeenCalledWith(expect.any(Function), 900);
    expect(typeof scheduledRedirect).toBe('function');
    act(() => {
      (scheduledRedirect as () => void)();
    });
    expect(mockNavigate).toHaveBeenCalledWith('/login', {replace: true});
  });

  it('verifies and confirms authenticated password changes before returning to account', async () => {
    const authValue = {
      ...mockUseAuth(),
      isAuthenticated: true,
      verifyPasswordChangeCode: vi.fn().mockResolvedValue({verification_token: 'change-token'}),
      confirmPasswordChange: vi.fn().mockResolvedValue({message: 'Password changed.'}),
    };
    mockUseAuth.mockReturnValue(authValue);

    render(
      <MemoryRouter initialEntries={['/verify-email?flow=change&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '112233'}});
    fireEvent.click(screen.getByRole('button', {name: 'Verify Code'}));

    expect(await screen.findByText('Code verified. Set your new password below.')).toBeInTheDocument();
    let scheduledRedirect: TimerHandler | undefined;
    const timeoutSpy = vi.spyOn(window, 'setTimeout').mockImplementation((handler: TimerHandler) => {
      scheduledRedirect = handler;
      return 0 as unknown as number;
    });
    fireEvent.change(screen.getByLabelText('New Password'), {target: {value: 'new-secret'}});
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'new-secret'}});
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Change Password'}));
      await Promise.resolve();
    });

    expect(authValue.confirmPasswordChange).toHaveBeenCalledWith('change-token', 'new-secret', 'new-secret');
    expect(screen.getByText('Password changed.')).toBeInTheDocument();
    expect(timeoutSpy).toHaveBeenCalledWith(expect.any(Function), 900);
    expect(typeof scheduledRedirect).toBe('function');
    act(() => {
      (scheduledRedirect as () => void)();
    });
    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
  });

  it.each([
    ['login', 'requestLoginCode'],
    ['register', 'resendRegistrationCode'],
    ['reset', 'requestPasswordReset'],
    ['change', 'requestPasswordChangeCode'],
  ] as const)('resends %s verification codes through the matching auth action', async (flow, actionName) => {
    const authValue = {
      ...mockUseAuth(),
      isAuthenticated: flow === 'change',
      [actionName]: vi.fn().mockResolvedValue({message: `${flow} code resent.`}),
    };
    mockUseAuth.mockReturnValue(authValue);

    render(
      <MemoryRouter initialEntries={[`/verify-email?flow=${flow}&email=ada@example.com`]}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

    await waitFor(() => {
      expect(authValue[actionName]).toHaveBeenCalledWith('ada@example.com');
    });
    expect(await screen.findByText(`${flow} code resent.`)).toBeInTheDocument();
  });

  it('navigates back to the correct source page for reset and change flows', () => {
    mockUseAuth.mockReturnValue({
      ...mockUseAuth(),
      isAuthenticated: true,
    });

    const {unmount} = render(
      <MemoryRouter initialEntries={['/verify-email?flow=change&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Back to account'}));
    expect(mockNavigate).toHaveBeenCalledWith('/account');

    unmount();
    mockNavigate.mockClear();
    mockUseAuth.mockReturnValue({
      ...mockUseAuth(),
      isAuthenticated: false,
    });

    render(
      <MemoryRouter initialEntries={['/verify-email?flow=reset&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Back'}));
    expect(mockNavigate).toHaveBeenCalledWith('/forgot-password');
  });

  it('resends auth codes through the email-auth endpoint with the login source', async () => {
    render(
      <MemoryRouter initialEntries={['/verify-email?flow=auth&email=ada@example.com']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const authValue = mockUseAuth.mock.results.at(-1)?.value;
    authValue.requestEmailAuthCode.mockResolvedValue({message: 'Code resent.'});

    const resendButtons = screen.getAllByRole('button', {name: 'Resend code'});
    fireEvent.click(resendButtons.at(-1)!);

    await waitFor(() => {
      expect(authValue.requestEmailAuthCode).toHaveBeenCalledWith('ada@example.com', 'login');
    });

    expect(await screen.findByText('Code resent.')).toBeInTheDocument();
  });
});
