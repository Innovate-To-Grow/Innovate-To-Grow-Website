import {render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {EmailAuthLinkPage} from './EmailAuthLinkPage';

const mockConsumeEmailAuthQuery = vi.fn();
const mockNavigate = vi.fn();
const mockDispatchAuthStateChange = vi.fn();

vi.mock('../../services/auth', () => ({
  consumeEmailAuthQuery: (...args: unknown[]) => mockConsumeEmailAuthQuery(...args),
}));

vi.mock('../../components/Auth/context/shared', () => ({
  dispatchAuthStateChange: () => mockDispatchAuthStateChange(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('EmailAuthLinkPage', () => {
  beforeEach(() => {
    mockConsumeEmailAuthQuery.mockReset();
    mockNavigate.mockReset();
    mockDispatchAuthStateChange.mockReset();
  });

  it('routes subscribe email links to the profile step when completion is required', async () => {
    mockConsumeEmailAuthQuery.mockResolvedValue({
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
      expect(mockConsumeEmailAuthQuery).toHaveBeenCalledWith({
        flow: 'auth',
        email: 'ada@example.com',
        code: '123456',
      });
    });

    expect(mockDispatchAuthStateChange).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/subscribe?step=profile', {replace: true});
  });

  it('routes event registration links back to the registration page', async () => {
    mockConsumeEmailAuthQuery.mockResolvedValue({
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
      expect(mockNavigate).toHaveBeenCalledWith('/event-registration', {replace: true});
    });
  });

  it('routes login email links through the login verify flow and into the account page', async () => {
    mockConsumeEmailAuthQuery.mockResolvedValue({
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
      expect(mockConsumeEmailAuthQuery).toHaveBeenCalledWith({
        flow: 'login',
        email: 'ada@example.com',
        code: '123456',
      });
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
    expect(mockConsumeEmailAuthQuery).not.toHaveBeenCalled();
  });

  it('shows an error when the verification code is invalid, expired, or already used', async () => {
    mockConsumeEmailAuthQuery.mockRejectedValue(new Error('expired'));

    render(
      <MemoryRouter initialEntries={['/email-auth-link?flow=auth&source=login&email=ada%40example.com&code=123456']}>
        <Routes>
          <Route path="/email-auth-link" element={<EmailAuthLinkPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByText('This email link is invalid, expired, or has already been used. Please request a new code.'),
      ).toBeInTheDocument();
    });

    expect(mockDispatchAuthStateChange).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
