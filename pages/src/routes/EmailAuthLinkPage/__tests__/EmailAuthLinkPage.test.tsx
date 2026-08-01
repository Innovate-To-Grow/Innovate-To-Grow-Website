import {render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {EmailAuthLinkPage} from '../EmailAuthLinkPage';

const mockVerifyEmailAuthCode = vi.fn();
const mockNavigate = vi.fn();
const mockDispatchAuthStateChange = vi.fn();

vi.mock('@/features/auth', () => ({
  verifyEmailAuthCode: (...args: unknown[]) => mockVerifyEmailAuthCode(...args),
}));

vi.mock('@/features/auth/components/context/shared', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth/components/context/shared')>('@/features/auth/components/context/shared');
  return {
    ...actual,
    dispatchAuthStateChange: () => mockDispatchAuthStateChange(),
  };
});

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('EmailAuthLinkPage', () => {
  beforeEach(() => {
    mockVerifyEmailAuthCode.mockReset();
    mockNavigate.mockReset();
    mockDispatchAuthStateChange.mockReset();
  });

  it('routes subscribe email links to the profile step when completion is required', async () => {
    mockVerifyEmailAuthCode.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
    });

    render(
      <MemoryRouter initialEntries={['/email-auth-link?flow=auth&source=subscribe&email=ada%40example.com&code=123456']}>
        <Routes>
          <Route path="/email-auth-link" element={<EmailAuthLinkPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockVerifyEmailAuthCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    expect(mockDispatchAuthStateChange).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/subscribe?step=profile', {replace: true});
  });

  it('routes incomplete event registration links through complete-profile first', async () => {
    mockVerifyEmailAuthCode.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
    });

    render(
      <MemoryRouter initialEntries={['/email-auth-link?flow=auth&source=event_registration&email=ada%40example.com&code=123456']}>
        <Routes>
          <Route path="/email-auth-link" element={<EmailAuthLinkPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fevent-registration', {replace: true});
    });
  });

  it('carries the event slug from the link back to the registration page', async () => {
    mockVerifyEmailAuthCode.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      next_step: 'account',
      requires_profile_completion: false,
    });

    render(
      <MemoryRouter initialEntries={['/email-auth-link?flow=auth&source=event_registration&email=ada%40example.com&code=123456&event=fall-showcase']}>
        <Routes>
          <Route path="/email-auth-link" element={<EmailAuthLinkPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/event-registration?event=fall-showcase', {replace: true});
    });
  });

  it('uses unified server-side verification even when the link contains a login flow hint', async () => {
    mockVerifyEmailAuthCode.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: '123', email: 'ada@example.com'},
      next_step: 'account',
      requires_profile_completion: false,
    });

    render(
      <MemoryRouter initialEntries={['/email-auth-link?flow=login&source=login&email=ada%40example.com&code=123456']}>
        <Routes>
          <Route path="/email-auth-link" element={<EmailAuthLinkPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockVerifyEmailAuthCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    expect(mockDispatchAuthStateChange).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/account', {replace: true});
  });

  it('shows an error for incomplete query parameters', async () => {
    render(
      <MemoryRouter initialEntries={['/email-auth-link?flow=auth&source=login&email=ada%40example.com']}>
        <Routes>
          <Route path="/email-auth-link" element={<EmailAuthLinkPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('This email link is invalid or incomplete.')).toBeInTheDocument();
    expect(mockVerifyEmailAuthCode).not.toHaveBeenCalled();
  });

  it('shows the backend validation error when the verification code is invalid or expired', async () => {
    mockVerifyEmailAuthCode.mockRejectedValue({
      response: {
        status: 400,
        data: {detail: 'Verification code is invalid or has expired.'},
      },
    });

    render(
      <MemoryRouter initialEntries={['/email-auth-link?flow=auth&source=login&email=ada%40example.com&code=123456']}>
        <Routes>
          <Route path="/email-auth-link" element={<EmailAuthLinkPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('Verification code is invalid or has expired.')).toBeInTheDocument();
    });

    expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('shows a transient error message when verification fails for non-code reasons', async () => {
    mockVerifyEmailAuthCode.mockRejectedValue({
      response: {
        status: 503,
        data: {},
      },
    });

    render(
      <MemoryRouter initialEntries={['/email-auth-link?flow=auth&source=login&email=ada%40example.com&code=123456']}>
        <Routes>
          <Route path="/email-auth-link" element={<EmailAuthLinkPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('A server error occurred. Please try again later.')).toBeInTheDocument();
    });

    expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
