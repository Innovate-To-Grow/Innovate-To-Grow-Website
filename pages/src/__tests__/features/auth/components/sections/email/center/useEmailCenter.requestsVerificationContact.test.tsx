import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {FormEvent} from 'react';

import {useEmailCenter} from '@/features/auth/components/sections/email/useEmailCenter';
import {baseProfile} from '@/__tests__/features/auth/components/sections/email/center/useEmailCenterFixtures';

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

const formEvent = () => ({preventDefault: vi.fn()}) as unknown as FormEvent;

describe('useEmailCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getContactEmails.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it('requests verification for a contact and opens the inline form', async () => {
    mocks.requestContactEmailVerification.mockResolvedValue({message: 'sent'});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleContactRequestVerification('e-1');
    });

    expect(result.current.verifyingId).toBe('e-1');
    expect(result.current.successMessage).toBe('Code sent. Enter it below and tap Submit code.');
  });

  it('surfaces an error when requesting contact verification fails', async () => {
    mocks.requestContactEmailVerification.mockRejectedValue({response: {data: {detail: 'Request failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleContactRequestVerification('e-1');
    });

    expect(result.current.error).toBe('Request failed');
  });

  it('opens primary verification', async () => {
    mocks.requestContactEmailVerification.mockResolvedValue({message: 'sent'});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryToggleVerify();
    });

    expect(mocks.requestContactEmailVerification).toHaveBeenCalledWith('pe-1');
    expect(result.current.primaryVerifying).toBe(true);
    expect(result.current.successMessage).toBe('Verification code sent to your primary email.');
  });

  it('does nothing to primary verification without a primary email id', async () => {
    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile({primary_email_id: null}), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryToggleVerify();
    });

    expect(mocks.requestContactEmailVerification).not.toHaveBeenCalled();
  });

  it('surfaces an error when opening primary verification fails', async () => {
    mocks.requestContactEmailVerification.mockRejectedValue({response: {data: {detail: 'Primary request failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryToggleVerify();
    });

    expect(result.current.error).toBe('Primary request failed');
  });

  it('submits primary verification and refreshes the profile', async () => {
    const updatedProfile = baseProfile({email_verified: true});
    mocks.requestContactEmailVerification.mockResolvedValue({message: 'sent'});
    mocks.verifyContactEmailCode.mockResolvedValue({message: 'verified'});
    mocks.getProfile.mockResolvedValue(updatedProfile);
    const onProfileUpdate = vi.fn();

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryToggleVerify();
    });
    act(() => result.current.setPrimaryVerifyCode('123456'));
    await act(async () => {
      await result.current.handlePrimaryVerifySubmit(formEvent());
    });

    expect(mocks.verifyContactEmailCode).toHaveBeenCalledWith('pe-1', '123456');
    expect(onProfileUpdate).toHaveBeenCalledWith(updatedProfile);
    expect(result.current.primaryVerifying).toBe(false);
    expect(result.current.successMessage).toBe('Primary email verified successfully.');
  });

  it('ignores primary verify submit without a primary id or full code', async () => {
    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile({primary_email_id: null}), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryVerifySubmit(formEvent());
    });

    act(() => {
      result.current.setPrimaryVerifyCode('123');
    });
    await act(async () => {
      await result.current.handlePrimaryVerifySubmit(formEvent());
    });

    expect(mocks.verifyContactEmailCode).not.toHaveBeenCalled();
  });

  it('surfaces a primary verify error', async () => {
    mocks.requestContactEmailVerification.mockResolvedValue({message: 'sent'});
    mocks.verifyContactEmailCode.mockRejectedValue({response: {data: {detail: 'Primary bad code'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryToggleVerify();
    });
    act(() => result.current.setPrimaryVerifyCode('123456'));
    await act(async () => {
      await result.current.handlePrimaryVerifySubmit(formEvent());
    });

    expect(result.current.primaryVerifyError).toBe('Primary bad code');
  });
});
