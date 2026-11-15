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

  it('verifies a pending phone and prepends it to the list', async () => {
    const pending = phone({id: 'pending-1', verified: false, subscribe: false});
    const verified = phone({id: 'pending-1', verified: true, subscribe: false});
    mocks.createContactPhone.mockResolvedValue(pending);
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});
    mocks.verifyContactPhoneCode.mockResolvedValue(verified);

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

    act(() => result.current.setVerifyCode('123456'));
    await act(async () => {
      await result.current.handleVerifySubmit(formEvent());
    });

    expect(mocks.verifyContactPhoneCode).toHaveBeenCalledWith('pending-1', '123456');
    expect(result.current.phones).toEqual([verified]);
    expect(result.current.pendingNewPhone).toBeNull();
    expect(result.current.showAddForm).toBe(false);
    expect(result.current.successMessage).toBe('Phone number verified successfully.');
  });

  it('resets the form when beginning the add-phone flow', async () => {
    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setAddPhoneNumber('5551234567');
      result.current.setAddSubscribe(true);
      result.current.setAddTermsAccepted(true);
      result.current.setAddError('stale');
    });
    act(() => result.current.beginAddPhoneFlow());

    expect(result.current.showAddForm).toBe(true);
    expect(result.current.pendingNewPhone).toBeNull();
    expect(result.current.verifyingId).toBeNull();
    expect(result.current.addPhoneNumber).toBe('');
    expect(result.current.addSubscribe).toBe(false);
    expect(result.current.addTermsAccepted).toBe(false);
    expect(result.current.addError).toBeNull();
  });

  it('keeps the form open with an error when submitting without a phone number', async () => {
    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setAddPhoneNumber('');
      result.current.setAddTermsAccepted(true);
      result.current.setShowAddForm(true);
      result.current.setAddSubscribe(true);
    });
    await act(async () => {
      await result.current.handleAddSubmit(formEvent());
    });

    expect(result.current.showAddForm).toBe(true);
    expect(result.current.addError).toBe('Enter a 10-digit US phone number.');
    expect(mocks.createContactPhone).not.toHaveBeenCalled();
  });

  it('syncs a changed subscription before verifying a pending phone', async () => {
    const pending = phone({id: 'pending-1', verified: false, subscribe: false});
    const verified = phone({id: 'pending-1', verified: true, subscribe: true});
    mocks.createContactPhone.mockResolvedValue(pending);
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});
    mocks.updateContactPhone.mockResolvedValue(phone({id: 'pending-1', verified: false, subscribe: true}));
    mocks.verifyContactPhoneCode.mockResolvedValue(verified);

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

    act(() => {
      result.current.setAddSubscribe(true);
      result.current.setVerifyCode('123456');
    });
    await act(async () => {
      await result.current.handleVerifySubmit(formEvent());
    });

    expect(mocks.updateContactPhone).toHaveBeenCalledWith('pending-1', {subscribe: true});
    expect(mocks.verifyContactPhoneCode).toHaveBeenCalledWith('pending-1', '123456');
    expect(result.current.phones).toEqual([verified]);
  });
});
