import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {useEmailCenter} from '@/features/auth/components/sections/email/useEmailCenter';
import {baseProfile, contactEmail} from '@/__tests__/features/auth/components/sections/email/center/useEmailCenterFixtures';

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

describe('useEmailCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getContactEmails.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it('resends the primary verification code', async () => {
    mocks.requestContactEmailVerification.mockResolvedValue({message: 'sent'});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryResend();
    });

    expect(mocks.requestContactEmailVerification).toHaveBeenCalledWith('pe-1');
    expect(result.current.successMessage).toBe('Verification code resent.');
  });

  it('does nothing on primary resend without a primary email id', async () => {
    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile({primary_email_id: null}), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryResend();
    });

    expect(mocks.requestContactEmailVerification).not.toHaveBeenCalled();
  });

  it('surfaces a primary resend error', async () => {
    mocks.requestContactEmailVerification.mockRejectedValue({response: {data: {detail: 'Primary resend failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryResend();
    });

    expect(result.current.primaryVerifyError).toBe('Primary resend failed');
  });

  it('cancels primary verification', async () => {
    mocks.requestContactEmailVerification.mockResolvedValue({message: 'sent'});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryToggleVerify();
    });
    act(() => result.current.setPrimaryVerifyCode('123456'));
    act(() => result.current.handlePrimaryCancelVerify());

    expect(result.current.primaryVerifying).toBe(false);
    expect(result.current.primaryVerifyCode).toBe('');
  });

  it('makes a contact primary and refreshes the list', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.makeContactEmailPrimary.mockResolvedValue({message: 'done'});
    mocks.getProfile.mockResolvedValue(baseProfile({email: 'secondary@example.com', primary_email_id: 'e-1'}));
    mocks.getContactEmails.mockResolvedValue([]);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleMakePrimary('e-1');
    });

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('your primary email?'));
    expect(mocks.makeContactEmailPrimary).toHaveBeenCalledWith('e-1');
    expect(mocks.getProfile).toHaveBeenCalled();
    expect(mocks.getContactEmails).toHaveBeenCalled();
    expect(result.current.successMessage).toBe(
      'Primary email updated. Your previous primary address is now listed as a connected email.',
    );
  });

  it('does not change the primary email when the confirmation is cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleMakePrimary('e-1');
    });

    expect(mocks.makeContactEmailPrimary).not.toHaveBeenCalled();
    expect(result.current.makePrimaryLoadingId).toBeNull();
  });

  it('surfaces a make-primary error', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.makeContactEmailPrimary.mockRejectedValue({response: {data: {detail: 'Make primary failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleMakePrimary('e-1');
    });

    expect(result.current.error).toBe('Make primary failed');
  });

  it('deletes a contact email and clears its verification state', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.getContactEmails.mockResolvedValue([contactEmail()]);
    mocks.deleteContactEmail.mockResolvedValue(undefined);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setVerifyingId('e-1'));
    await act(async () => {
      await result.current.handleDelete('e-1');
    });

    expect(mocks.deleteContactEmail).toHaveBeenCalledWith('e-1');
    expect(result.current.contactEmails).toEqual([]);
    expect(result.current.verifyingId).toBeNull();
    expect(result.current.successMessage).toBe('Email removed.');
  });

  it('does not delete a contact when confirm is cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleDelete('e-1');
    });

    expect(mocks.deleteContactEmail).not.toHaveBeenCalled();
  });
});
