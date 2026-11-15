import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {FormEvent} from 'react';

import type {ContactPhone} from '@/features/auth/api';
import {usePhoneCenter} from '@/features/auth/components/sections/phone/usePhoneCenter';

const mocks = vi.hoisted(() => ({
  getContactPhones: vi.fn(),
  createContactPhone: vi.fn(),
  updateContactPhone: vi.fn(),
  deleteContactPhone: vi.fn(),
  requestContactPhoneVerification: vi.fn(),
  verifyContactPhoneCode: vi.fn(),
}));

vi.mock('@/features/auth/api', () => ({
  getContactPhones: () => mocks.getContactPhones(),
  createContactPhone: (data: unknown) => mocks.createContactPhone(data),
  updateContactPhone: (id: string, data: unknown) => mocks.updateContactPhone(id, data),
  deleteContactPhone: (id: string) => mocks.deleteContactPhone(id),
  requestContactPhoneVerification: (id: string) => mocks.requestContactPhoneVerification(id),
  verifyContactPhoneCode: (id: string, code: string) => mocks.verifyContactPhoneCode(id, code),
}));

const phone = (overrides: Partial<ContactPhone> = {}): ContactPhone => ({
  id: 'p-1',
  phone_number: '5551234567',
  region: '1-US',
  region_display: 'United States',
  subscribe: false,
  verified: true,
  created_at: '2026-01-02T00:00:00Z',
  ...overrides,
});

const formEvent = () => ({preventDefault: vi.fn()}) as unknown as FormEvent;

describe('usePhoneCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getContactPhones.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it('requires terms acceptance before verifying a pending phone', async () => {
    const pending = phone({id: 'pending-1', verified: false});
    mocks.getContactPhones.mockResolvedValue([]);

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setVerifyCode('123456');
      result.current.setAddTermsAccepted(false);
    });
    // pendingNewPhone is set via the add flow; simulate directly by calling add submit.
    mocks.createContactPhone.mockResolvedValue(pending);
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});
    act(() => {
      result.current.setAddPhoneNumber('5551234567');
      result.current.setAddTermsAccepted(true);
      result.current.setAddSubscribe(false);
    });
    await act(async () => {
      await result.current.handleAddSubmit(formEvent());
    });
    // Now un-accept terms to exercise the pending-verify guard.
    act(() => result.current.setAddTermsAccepted(false));
    act(() => result.current.setVerifyCode('123456'));
    await act(async () => {
      await result.current.handleVerifySubmit(formEvent());
    });

    expect(result.current.verifyError).toBe('Please accept the Privacy/Legal Notice and Privacy Statement to continue.');
    expect(mocks.verifyContactPhoneCode).not.toHaveBeenCalled();
  });

  it('surfaces a verify error for an existing phone', async () => {
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});
    mocks.verifyContactPhoneCode.mockRejectedValue(new Error('bad code'));

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleToggleVerify('p-1');
    });
    act(() => result.current.setVerifyCode('123456'));
    await act(async () => {
      await result.current.handleVerifySubmit(formEvent());
    });

    expect(result.current.verifyError).toBe('An unknown error occurred.');
  });

  it('resends a code for an existing phone and reports success', async () => {
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleResend('p-1');
    });

    expect(mocks.requestContactPhoneVerification).toHaveBeenCalledWith('p-1');
    expect(result.current.successMessage).toBe('New code sent. Enter it below and tap Submit code.');
  });

  it('surfaces a resend error', async () => {
    mocks.requestContactPhoneVerification.mockRejectedValue(new Error('boom'));

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleResend('p-1');
    });

    expect(result.current.verifyError).toBe('An unknown error occurred.');
  });

  it('resends the pending phone code without a success message', async () => {
    const pending = phone({id: 'pending-1', verified: false});
    mocks.createContactPhone.mockResolvedValue(pending);
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setAddPhoneNumber('5551234567');
      result.current.setAddTermsAccepted(true);
      result.current.setAddSubscribe(false);
    });
    await act(async () => {
      await result.current.handleAddSubmit(formEvent());
    });
    expect(result.current.pendingNewPhone?.id).toBe('pending-1');

    await act(async () => {
      await result.current.handleResendPendingPhone();
    });

    expect(mocks.requestContactPhoneVerification).toHaveBeenCalledWith('pending-1');
    expect(result.current.successMessage).toBeNull();
  });

  it('cancels verification', async () => {
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleToggleVerify('p-1');
    });
    act(() => result.current.setVerifyCode('123456'));
    act(() => result.current.handleCancelVerify());

    expect(result.current.verifyingId).toBeNull();
    expect(result.current.verifyCode).toBe('');
  });

  it('does nothing to abandon when there is no pending phone', async () => {
    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleAbandonPendingPhone();
    });

    expect(mocks.deleteContactPhone).not.toHaveBeenCalled();
  });
});
