import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {ContactEmail, ProfileResponse} from '@/features/auth/api';
import {EmailCenter} from '../EmailCenter';

const mocks = vi.hoisted(() => ({
  getContactEmails: vi.fn(),
  createContactEmail: vi.fn(),
  deleteContactEmail: vi.fn(),
  updateContactEmail: vi.fn(),
  makeContactEmailPrimary: vi.fn(),
  requestContactEmailVerification: vi.fn(),
  verifyContactEmailCode: vi.fn(),
  getProfile: vi.fn(),
  updateProfileFields: vi.fn(),
}));

vi.mock('@/features/auth/api', () => ({
  getContactEmails: () => mocks.getContactEmails(),
  createContactEmail: (data: unknown) => mocks.createContactEmail(data),
  deleteContactEmail: (id: string) => mocks.deleteContactEmail(id),
  updateContactEmail: (id: string, data: unknown) => mocks.updateContactEmail(id, data),
  makeContactEmailPrimary: (id: string) => mocks.makeContactEmailPrimary(id),
  requestContactEmailVerification: (id: string) => mocks.requestContactEmailVerification(id),
  verifyContactEmailCode: (id: string, code: string) => mocks.verifyContactEmailCode(id, code),
  getProfile: () => mocks.getProfile(),
  updateProfileFields: (data: unknown) => mocks.updateProfileFields(data),
}));

const baseProfile = (overrides: Partial<ProfileResponse> = {}): ProfileResponse => ({
  member_uuid: 'm-1',
  email: '',
  email_verified: false,
  primary_email_id: null,
  first_name: 'Pat',
  middle_name: '',
  last_name: 'Phone',
  organization: '',
  title: '',
  email_subscribe: true,
  is_staff: false,
  is_active: true,
  date_joined: '2026-01-01T00:00:00Z',
  ...overrides,
});

const contactEmail = (overrides: Partial<ContactEmail> = {}): ContactEmail => ({
  id: 'e-1',
  email_address: 'secondary@example.com',
  email_type: 'secondary',
  subscribe: true,
  verified: true,
  created_at: '2026-01-02T00:00:00Z',
  ...overrides,
});

describe('EmailCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getContactEmails.mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it('shows the account first email as the primary email', async () => {
    // A phone-first account whose first email was auto-assigned primary: it arrives
    // via profile.email and the contact list (which excludes primary) is empty.
    render(<EmailCenter profile={baseProfile({email: 'first@example.com'})} onProfileUpdate={vi.fn()} />);

    expect(await screen.findByText('first@example.com')).toBeInTheDocument();
    expect(screen.getByText('Primary')).toBeInTheDocument();
  });

  it('keeps the email and surfaces the error when deletion is blocked by the backend', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.getContactEmails.mockResolvedValue([contactEmail()]);
    mocks.deleteContactEmail.mockRejectedValue({
      response: {
        status: 409,
        data: {detail: 'You cannot remove your only verified recovery method. Add and verify another email or phone first.'},
      },
    });

    render(<EmailCenter profile={baseProfile({email: 'primary@example.com'})} onProfileUpdate={vi.fn()} />);

    const removeButton = await screen.findByRole('button', {name: 'Remove'});
    fireEvent.click(removeButton);

    await waitFor(() => {
      expect(mocks.deleteContactEmail).toHaveBeenCalledWith('e-1');
    });
    // The blocked email is retained and the actionable error is shown.
    expect(screen.getByText('secondary@example.com')).toBeInTheDocument();
    expect(screen.getByText(/verified recovery method/i)).toBeInTheDocument();
  });
});
