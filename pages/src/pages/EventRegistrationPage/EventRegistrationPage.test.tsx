import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {EventRegistrationPage} from './EventRegistrationPage';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();
const mockFetchRegistrationOptions = vi.fn();

vi.mock('../../components/Auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/Auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('../../features/events/api', async () => {
  const actual = await vi.importActual<typeof import('../../features/events/api')>('../../features/events/api');
  return {
    ...actual,
    fetchRegistrationOptions: (...args: unknown[]) => mockFetchRegistrationOptions(...args),
    createRegistration: vi.fn(),
    sendPhoneCode: vi.fn(),
    verifyPhoneCode: vi.fn(),
  };
});

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('EventRegistrationPage', () => {
  const requestEmailAuthCode = vi.fn();
  const verifyEmailAuthCode = vi.fn();

  beforeEach(() => {
    mockUseAuth.mockReset();
    mockNavigate.mockReset();
    mockFetchRegistrationOptions.mockReset();
    requestEmailAuthCode.mockReset();
    verifyEmailAuthCode.mockReset();

    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      requiresProfileCompletion: false,
      requestEmailAuthCode,
      verifyEmailAuthCode,
    });

    mockFetchRegistrationOptions.mockResolvedValue({
      id: 'event-1',
      name: 'Demo Day',
      slug: 'demo-day',
      date: '2026-05-01',
      location: 'Campus',
      description: 'Event description',
      allow_secondary_email: false,
      collect_phone: false,
      verify_phone: false,
      tickets: [],
      questions: [],
      registration: null,
      member_emails: [],
      member_profile: null,
      member_phone: null,
      phone_regions: [{code: '1-US', label: 'United States'}],
    });

    requestEmailAuthCode.mockResolvedValue({message: 'ok'});
    verifyEmailAuthCode.mockResolvedValue({
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: 'member-1', email: 'ada@example.com'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
    });
  });

  it('redirects incomplete email-auth signups to complete-profile before showing the form', async () => {
    render(
      <MemoryRouter initialEntries={['/event-registration']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByLabelText('Email');

    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'ada@example.com'}});
    fireEvent.submit(screen.getByRole('button', {name: 'Continue with Email'}).closest('form')!);

    await waitFor(() => {
      expect(requestEmailAuthCode).toHaveBeenCalledWith('ada@example.com', 'event_registration');
    });

    const codeInput = await screen.findByLabelText('Verification Code');
    fireEvent.change(codeInput, {target: {value: '123456'}});
    fireEvent.submit(screen.getByRole('button', {name: 'Verify Code'}).closest('form')!);

    await waitFor(() => {
      expect(verifyEmailAuthCode).toHaveBeenCalledWith('ada@example.com', '123456');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fevent-registration', {replace: true});
  });

  it('redirects authenticated members with incomplete names before loading the form', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      requiresProfileCompletion: true,
      requestEmailAuthCode,
      verifyEmailAuthCode,
    });

    render(
      <MemoryRouter initialEntries={['/event-registration']}>
        <Routes>
          <Route path="/event-registration" element={<EventRegistrationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/complete-profile?returnTo=%2Fevent-registration', {replace: true});
    });

    expect(mockFetchRegistrationOptions).not.toHaveBeenCalled();
  });
});
