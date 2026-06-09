import {act, renderHook, waitFor} from '@testing-library/react';
import type {FormEvent} from 'react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

const authApiMock = vi.hoisted(() => ({
  createContactEmail: vi.fn(),
  deleteContactEmail: vi.fn(),
  getContactEmails: vi.fn(),
  getProfile: vi.fn(),
  makeContactEmailPrimary: vi.fn(),
  requestContactEmailVerification: vi.fn(),
  updateContactEmail: vi.fn(),
  updateProfileFields: vi.fn(),
  verifyContactEmailCode: vi.fn(),
}));

vi.mock('@/features/auth/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth/api')>('@/features/auth/api');
  return {
    ...actual,
    createContactEmail: authApiMock.createContactEmail,
    deleteContactEmail: authApiMock.deleteContactEmail,
    getContactEmails: authApiMock.getContactEmails,
    getProfile: authApiMock.getProfile,
    makeContactEmailPrimary: authApiMock.makeContactEmailPrimary,
    requestContactEmailVerification: authApiMock.requestContactEmailVerification,
    updateContactEmail: authApiMock.updateContactEmail,
    updateProfileFields: authApiMock.updateProfileFields,
    verifyContactEmailCode: authApiMock.verifyContactEmailCode,
  };
});

import {useEmailCenter} from '@/features/auth/components/sections/internal/useEmailCenter';
import type {ContactEmail, ProfileResponse} from '@/features/auth/api';

const profile: ProfileResponse = {
  email: 'primary@example.com',
  first_name: 'Ada',
  last_name: 'Lovelace',
  middle_name: '',
  organization: 'UC Merced',
  title: '',
  profile_image: '',
  email_subscribe: true,
  primary_email_id: 'primary-id',
};

const secondary: ContactEmail = {
  id: 'secondary-id',
  email_address: 'secondary@example.com',
  email_type: 'secondary',
  subscribe: true,
  verified: false,
};

const other: ContactEmail = {
  id: 'other-id',
  email_address: 'other@example.com',
  email_type: 'other',
  subscribe: false,
  verified: true,
};

const renderEmailCenter = (onProfileUpdate = vi.fn()) =>
  renderHook(() => useEmailCenter({profile, onProfileUpdate}));

describe('useEmailCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    authApiMock.getContactEmails.mockResolvedValue([secondary, other]);
    authApiMock.updateProfileFields.mockResolvedValue({...profile, email_subscribe: false});
    authApiMock.updateContactEmail.mockImplementation(async (id: string, patch: Partial<ContactEmail>) => ({
      ...(id === secondary.id ? secondary : other),
      ...patch,
    }));
    authApiMock.createContactEmail.mockResolvedValue({
      id: 'created-id',
      email_address: 'new@example.com',
      email_type: 'other',
      subscribe: true,
      verified: false,
    });
    authApiMock.verifyContactEmailCode.mockResolvedValue({...secondary, verified: true});
    authApiMock.requestContactEmailVerification.mockResolvedValue({message: 'sent'});
    authApiMock.getProfile.mockResolvedValue({...profile, email: 'new-primary@example.com'});
    authApiMock.makeContactEmailPrimary.mockResolvedValue({...other, email_type: 'primary'});
    authApiMock.deleteContactEmail.mockResolvedValue(undefined);
  });

  it('loads contact emails and avoids a duplicate secondary add type', async () => {
    const {result} = renderEmailCenter();

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.contactEmails).toEqual([secondary, other]);
    expect(result.current.hasSecondaryEmail).toBe(true);
    await waitFor(() => expect(result.current.addType).toBe('other'));
  });

  it('toggles primary and contact subscription state', async () => {
    const onProfileUpdate = vi.fn();
    const {result} = renderEmailCenter(onProfileUpdate);
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimarySubscribeToggle();
    });
    expect(authApiMock.updateProfileFields).toHaveBeenCalledWith({email_subscribe: false});
    expect(onProfileUpdate).toHaveBeenCalledWith({...profile, email_subscribe: false});
    expect(result.current.successMessage).toBe('Primary email unsubscribed.');

    await act(async () => {
      await result.current.handleContactSubscribeToggle(other);
    });
    expect(authApiMock.updateContactEmail).toHaveBeenCalledWith(other.id, {subscribe: true});
    expect(result.current.contactEmails.find((item) => item.id === other.id)?.subscribe).toBe(true);
  });

  it('prevents duplicate secondary email assignments and updates valid types', async () => {
    const {result} = renderEmailCenter();
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleContactTypeChange(other, 'secondary');
    });
    expect(result.current.error).toBe('You already have a secondary email.');

    await act(async () => {
      await result.current.handleContactTypeChange(secondary, 'other');
    });
    expect(authApiMock.updateContactEmail).toHaveBeenCalledWith(secondary.id, {email_type: 'other'});
  });

  it('adds, verifies, resends, and requests verification for contact emails', async () => {
    const {result} = renderEmailCenter();
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setAddEmail(' new@example.com ');
      result.current.setAddType('other');
      result.current.setAddSubscribe(true);
    });
    await act(async () => {
      await result.current.handleAddSubmit({preventDefault: vi.fn()} as unknown as FormEvent);
    });

    expect(authApiMock.createContactEmail).toHaveBeenCalledWith({
      email_address: 'new@example.com',
      email_type: 'other',
      subscribe: true,
    });
    expect(result.current.verifyingId).toBe('created-id');
    expect(result.current.successMessage).toContain('Email added');

    act(() => result.current.setVerifyCode('123456'));
    await act(async () => {
      await result.current.handleVerifySubmit({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    expect(authApiMock.verifyContactEmailCode).toHaveBeenCalledWith('created-id', '123456');
    expect(result.current.verifyingId).toBeNull();
    expect(result.current.successMessage).toBe('Email verified successfully.');

    await act(async () => {
      await result.current.handleResend(secondary.id);
    });
    expect(authApiMock.requestContactEmailVerification).toHaveBeenCalledWith(secondary.id);

    await act(async () => {
      await result.current.handleContactRequestVerification(other.id);
    });
    expect(result.current.verifyingId).toBe(other.id);
  });

  it('handles primary email verification and make-primary flows', async () => {
    const onProfileUpdate = vi.fn();
    const {result} = renderEmailCenter(onProfileUpdate);
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryToggleVerify();
    });
    expect(result.current.primaryVerifying).toBe(true);

    act(() => result.current.setPrimaryVerifyCode('654321'));
    await act(async () => {
      await result.current.handlePrimaryVerifySubmit({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    expect(authApiMock.verifyContactEmailCode).toHaveBeenCalledWith('primary-id', '654321');
    expect(onProfileUpdate).toHaveBeenCalledWith({...profile, email: 'new-primary@example.com'});

    await act(async () => {
      await result.current.handlePrimaryResend();
    });
    expect(result.current.successMessage).toBe('Verification code resent.');

    act(() => result.current.handlePrimaryCancelVerify());
    expect(result.current.primaryVerifying).toBe(false);

    await act(async () => {
      await result.current.handleMakePrimary(other.id);
    });
    expect(authApiMock.makeContactEmailPrimary).toHaveBeenCalledWith(other.id);
    expect(authApiMock.getContactEmails).toHaveBeenCalledTimes(2);
  });

  it('deletes contact emails when confirmed and leaves them alone when cancelled', async () => {
    const {result} = renderEmailCenter();
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleDelete(other.id);
    });
    expect(authApiMock.deleteContactEmail).toHaveBeenCalledWith(other.id);
    expect(result.current.contactEmails.some((item) => item.id === other.id)).toBe(false);

    vi.mocked(window.confirm).mockReturnValueOnce(false);
    await act(async () => {
      await result.current.handleDelete(secondary.id);
    });
    expect(authApiMock.deleteContactEmail).toHaveBeenCalledTimes(1);
  });
});
