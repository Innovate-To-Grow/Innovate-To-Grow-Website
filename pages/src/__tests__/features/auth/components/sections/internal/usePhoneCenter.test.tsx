import {act, renderHook, waitFor} from '@testing-library/react';
import type {FormEvent} from 'react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

const authApiMock = vi.hoisted(() => ({
  createContactPhone: vi.fn(),
  deleteContactPhone: vi.fn(),
  getContactPhones: vi.fn(),
  requestContactPhoneVerification: vi.fn(),
  updateContactPhone: vi.fn(),
  verifyContactPhoneCode: vi.fn(),
}));

vi.mock('@/features/auth/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth/api')>('@/features/auth/api');
  return {
    ...actual,
    createContactPhone: authApiMock.createContactPhone,
    deleteContactPhone: authApiMock.deleteContactPhone,
    getContactPhones: authApiMock.getContactPhones,
    requestContactPhoneVerification: authApiMock.requestContactPhoneVerification,
    updateContactPhone: authApiMock.updateContactPhone,
    verifyContactPhoneCode: authApiMock.verifyContactPhoneCode,
  };
});

import {usePhoneCenter} from '@/features/auth/components/sections/internal/usePhoneCenter';
import type {ContactPhone} from '@/features/auth/api';

const phone: ContactPhone = {
  id: 'phone-id',
  phone_number: '+12095551212',
  region: '1-US',
  subscribe: true,
  verified: false,
};

const verifiedPhone: ContactPhone = {
  ...phone,
  verified: true,
};

describe('usePhoneCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    authApiMock.getContactPhones.mockResolvedValue([phone]);
    authApiMock.updateContactPhone.mockResolvedValue({...phone, subscribe: false});
    authApiMock.createContactPhone.mockResolvedValue({id: 'new-phone', phone_number: '2095551212', region: '1-US', subscribe: true, verified: false});
    authApiMock.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});
    authApiMock.verifyContactPhoneCode.mockResolvedValue(verifiedPhone);
    authApiMock.deleteContactPhone.mockResolvedValue(undefined);
  });

  it('loads existing phones and starts a clean add flow', async () => {
    const {result} = renderHook(() => usePhoneCenter());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.phones).toEqual([phone]);

    act(() => {
      result.current.beginAddPhoneFlow();
    });
    expect(result.current.showAddForm).toBe(true);
    expect(result.current.addPhoneNumber).toBe('');
    expect(result.current.addRegion).toBe('1-US');
    expect(result.current.addSubscribe).toBe(true);
  });

  it('caps national digits when changing regions', async () => {
    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setAddPhoneNumber('1234567890123');
      result.current.handleAddRegionChange('852');
    });

    expect(result.current.addRegion).toBe('852');
    expect(result.current.addPhoneNumber).toBe('12345678');
  });

  it('toggles subscriptions and reports update failures', async () => {
    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleSubscribeToggle(phone);
    });
    expect(authApiMock.updateContactPhone).toHaveBeenCalledWith(phone.id, {subscribe: false});
    expect(result.current.phones[0].subscribe).toBe(false);

    authApiMock.updateContactPhone.mockRejectedValueOnce(new Error('bad'));
    await act(async () => {
      await result.current.handleSubscribeToggle(phone);
    });
    expect(result.current.error).toBe('An unknown error occurred.');
  });

  it('adds a phone, requests SMS verification, and verifies pending additions', async () => {
    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleAddSubmit({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    expect(authApiMock.createContactPhone).not.toHaveBeenCalled();

    act(() => {
      result.current.setAddPhoneNumber('2095551212');
      result.current.setAddRegion('1-US');
      result.current.setAddSubscribe(true);
    });
    await act(async () => {
      await result.current.handleAddSubmit({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    expect(authApiMock.createContactPhone).toHaveBeenCalledWith({
      phone_number: '2095551212',
      region: '1-US',
      subscribe: true,
    });
    expect(result.current.pendingNewPhone?.id).toBe('new-phone');
    expect(result.current.verifyingId).toBe('new-phone');

    act(() => result.current.setVerifyCode('123456'));
    authApiMock.verifyContactPhoneCode.mockResolvedValueOnce({...verifiedPhone, id: 'new-phone'});
    await act(async () => {
      await result.current.handleVerifySubmit({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    expect(result.current.pendingNewPhone).toBeNull();
    expect(result.current.showAddForm).toBe(false);
    expect(result.current.phones[0].id).toBe('new-phone');
  });

  it('handles verification requests, resend, cancel, abandon, and delete', async () => {
    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleToggleVerify(phone.id);
    });
    expect(result.current.verifyingId).toBe(phone.id);
    expect(result.current.successMessage).toBe('Code sent. Enter it below and tap Submit code.');

    await act(async () => {
      await result.current.handleResend(phone.id);
    });
    expect(result.current.successMessage).toBe('New code sent. Enter it below and tap Submit code.');

    act(() => result.current.handleCancelVerify());
    expect(result.current.verifyingId).toBeNull();

    act(() => {
      result.current.setAddPhoneNumber('2095551212');
    });
    await act(async () => {
      await result.current.handleAddSubmit({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    await act(async () => {
      await result.current.handleResendPendingPhone();
    });
    await act(async () => {
      await result.current.handleAbandonPendingPhone();
    });
    expect(authApiMock.deleteContactPhone).toHaveBeenCalledWith('new-phone');
    expect(result.current.pendingNewPhone).toBeNull();

    await act(async () => {
      await result.current.handleDelete(phone.id);
    });
    expect(result.current.phones.some((item) => item.id === phone.id)).toBe(false);
    expect(result.current.successMessage).toBe('Phone number removed.');

    vi.mocked(window.confirm).mockReturnValueOnce(false);
    await act(async () => {
      await result.current.handleDelete('missing');
    });
    expect(authApiMock.deleteContactPhone).toHaveBeenCalledTimes(2);
  });

  it('surfaces add and verification failures', async () => {
    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    authApiMock.createContactPhone.mockRejectedValueOnce(new Error('bad'));
    act(() => result.current.setAddPhoneNumber('2095551212'));
    await act(async () => {
      await result.current.handleAddSubmit({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    expect(result.current.addError).toBe('An unknown error occurred.');

    await act(async () => {
      await result.current.handleToggleVerify(phone.id);
    });
    act(() => result.current.setVerifyCode('123456'));
    authApiMock.verifyContactPhoneCode.mockRejectedValueOnce(new Error('bad code'));
    await act(async () => {
      await result.current.handleVerifySubmit({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    expect(result.current.verifyError).toBe('An unknown error occurred.');
  });
});
