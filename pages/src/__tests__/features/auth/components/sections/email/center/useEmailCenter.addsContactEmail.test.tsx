import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {FormEvent} from 'react';

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

const formEvent = () => ({preventDefault: vi.fn()}) as unknown as FormEvent;

describe('useEmailCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getContactEmails.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it('adds a contact email and opens verification for it', async () => {
    const created = contactEmail({id: 'new-1', verified: false});
    mocks.createContactEmail.mockResolvedValue(created);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setAddEmail(' new@example.com ');
      result.current.setAddType('secondary');
      result.current.setAddSubscribe(true);
      result.current.setShowAddForm(true);
    });
    await act(async () => {
      await result.current.handleAddSubmit(formEvent());
    });

    expect(mocks.createContactEmail).toHaveBeenCalledWith({
      email_address: 'new@example.com',
      email_type: 'secondary',
      subscribe: true,
    });
    expect(result.current.verifyingId).toBe('new-1');
    expect(result.current.showAddForm).toBe(false);
    expect(result.current.successMessage).toBe(
      'Email added. Please enter the verification code sent to your email.',
    );
  });

  it('surfaces an add error without changing state', async () => {
    mocks.createContactEmail.mockRejectedValue({response: {data: {detail: 'Add failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setAddEmail('new@example.com');
      result.current.setShowAddForm(true);
    });
    await act(async () => {
      await result.current.handleAddSubmit(formEvent());
    });

    expect(result.current.addError).toBe('Add failed');
    expect(result.current.verifyingId).toBeNull();
  });

  it('verifies a contact email code', async () => {
    const updated = contactEmail({verified: true});
    mocks.verifyContactEmailCode.mockResolvedValue(updated);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setVerifyingId('e-1');
      result.current.setVerifyCode('123456');
    });
    await act(async () => {
      await result.current.handleVerifySubmit(formEvent());
    });

    expect(mocks.verifyContactEmailCode).toHaveBeenCalledWith('e-1', '123456');
    expect(result.current.verifyingId).toBeNull();
    expect(result.current.successMessage).toBe('Email verified successfully.');
  });

  it('ignores verify submit without a target id or a full code', async () => {
    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleVerifySubmit(formEvent());
    });

    act(() => {
      result.current.setVerifyingId('e-1');
      result.current.setVerifyCode('123');
    });
    await act(async () => {
      await result.current.handleVerifySubmit(formEvent());
    });

    expect(mocks.verifyContactEmailCode).not.toHaveBeenCalled();
  });

  it('surfaces a verify error', async () => {
    mocks.verifyContactEmailCode.mockRejectedValue({response: {data: {detail: 'Bad code'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setVerifyingId('e-1');
      result.current.setVerifyCode('123456');
    });
    await act(async () => {
      await result.current.handleVerifySubmit(formEvent());
    });

    expect(result.current.verifyError).toBe('Bad code');
  });

  it('resends a contact verification code', async () => {
    mocks.requestContactEmailVerification.mockResolvedValue({message: 'sent'});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleResend('e-1');
    });

    expect(mocks.requestContactEmailVerification).toHaveBeenCalledWith('e-1');
    expect(result.current.successMessage).toBe('New code sent. Enter it below and tap Submit code.');
  });

  it('surfaces a resend error', async () => {
    mocks.requestContactEmailVerification.mockRejectedValue({response: {data: {detail: 'Resend failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleResend('e-1');
    });

    expect(result.current.verifyError).toBe('Resend failed');
  });
});
