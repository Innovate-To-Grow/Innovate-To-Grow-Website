import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
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

describe('useEmailCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getContactEmails.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it('surfaces a delete error', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.deleteContactEmail.mockRejectedValue({response: {data: {detail: 'Delete failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleDelete('e-1');
    });

    expect(result.current.error).toBe('Delete failed');
  });

  it('deletes the primary email and refreshes profile and list', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.deleteContactEmail.mockResolvedValue(undefined);
    mocks.getProfile.mockResolvedValue(baseProfile({email: '', primary_email_id: null}));
    mocks.getContactEmails.mockResolvedValue([]);
    const onProfileUpdate = vi.fn();

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryDelete();
    });

    expect(mocks.deleteContactEmail).toHaveBeenCalledWith('pe-1');
    expect(onProfileUpdate).toHaveBeenCalledWith(baseProfile({email: '', primary_email_id: null}));
    expect(result.current.successMessage).toBe('Email removed.');
  });

  it('does nothing on primary delete without a primary email id or confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile({primary_email_id: null}), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryDelete();
    });

    expect(mocks.deleteContactEmail).not.toHaveBeenCalled();
  });

  it('surfaces a primary delete error', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.deleteContactEmail.mockRejectedValue({response: {data: {detail: 'Primary delete failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimaryDelete();
    });

    expect(result.current.error).toBe('Primary delete failed');
  });

  it('clears error and success messages', async () => {
    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.clearMessages());
    expect(result.current.error).toBeNull();
    expect(result.current.successMessage).toBeNull();
  });
});
