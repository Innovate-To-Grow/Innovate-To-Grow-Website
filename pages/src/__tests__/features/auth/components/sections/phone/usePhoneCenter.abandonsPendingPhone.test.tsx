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

  it('abandons a pending phone', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.deleteContactPhone.mockResolvedValue(undefined);
    const pending = phone({id: 'pending-1', verified: false});

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    // Drive the add flow to establish pendingNewPhone.
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
    expect(result.current.pendingNewPhone?.id).toBe('pending-1');

    await act(async () => {
      await result.current.handleAbandonPendingPhone();
    });

    expect(mocks.deleteContactPhone).toHaveBeenCalledWith('pending-1');
    expect(result.current.pendingNewPhone).toBeNull();
    expect(result.current.verifyingId).toBeNull();
  });

  it('does not abandon a pending phone when confirm is cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const pending = phone({id: 'pending-1', verified: false});

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    mocks.createContactPhone.mockResolvedValue(pending);
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});
    act(() => {
      result.current.setAddPhoneNumber('5551234567');
      result.current.setAddTermsAccepted(true);
    });
    await act(async () => {
      await result.current.handleAddSubmit(formEvent());
    });

    await act(async () => {
      await result.current.handleAbandonPendingPhone();
    });

    expect(mocks.deleteContactPhone).not.toHaveBeenCalled();
  });

  it('surfaces an error when abandoning a pending phone fails', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.deleteContactPhone.mockRejectedValue(new Error('boom'));
    const pending = phone({id: 'pending-1', verified: false});

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    mocks.createContactPhone.mockResolvedValue(pending);
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});
    act(() => {
      result.current.setAddPhoneNumber('5551234567');
      result.current.setAddTermsAccepted(true);
    });
    await act(async () => {
      await result.current.handleAddSubmit(formEvent());
    });

    await act(async () => {
      await result.current.handleAbandonPendingPhone();
    });

    expect(result.current.error).toBe('An unknown error occurred.');
  });

  it('deletes a phone and clears its verification state', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.getContactPhones.mockResolvedValue([phone()]);
    mocks.deleteContactPhone.mockResolvedValue(undefined);
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleToggleVerify('p-1');
    });
    await act(async () => {
      await result.current.handleDelete('p-1');
    });

    expect(mocks.deleteContactPhone).toHaveBeenCalledWith('p-1');
    expect(result.current.phones).toEqual([]);
    expect(result.current.verifyingId).toBeNull();
    expect(result.current.successMessage).toBe('Phone number removed.');
  });

  it('does not delete a phone when confirm is cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleDelete('p-1');
    });

    expect(mocks.deleteContactPhone).not.toHaveBeenCalled();
  });

  it('surfaces a generic error when deleting a phone fails', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.deleteContactPhone.mockRejectedValue(new Error('boom'));

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleDelete('p-1');
    });

    expect(result.current.error).toBe('An unknown error occurred.');
  });
});
