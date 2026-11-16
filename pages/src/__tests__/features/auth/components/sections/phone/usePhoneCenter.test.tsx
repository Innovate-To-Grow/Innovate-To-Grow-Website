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

  it('loads phones and stops loading', async () => {
    mocks.getContactPhones.mockResolvedValue([phone()]);

    const {result} = renderHook(() => usePhoneCenter());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.phones).toEqual([phone()]);
  });

  it('stays empty and silent when the initial fetch fails', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    mocks.getContactPhones.mockRejectedValue(new Error('boom'));

    const {result} = renderHook(() => usePhoneCenter());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.phones).toEqual([]);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it('toggles a phone subscription', async () => {
    mocks.getContactPhones.mockResolvedValue([phone()]);
    const updated = phone({subscribe: true});
    mocks.updateContactPhone.mockResolvedValue(updated);

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleSubscribeToggle(phone());
    });

    expect(mocks.updateContactPhone).toHaveBeenCalledWith('p-1', {subscribe: true});
    expect(result.current.phones).toEqual([updated]);
  });

  it('surfaces a generic error when toggling a phone subscription fails', async () => {
    mocks.updateContactPhone.mockRejectedValue(new Error('boom'));

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleSubscribeToggle(phone());
    });

    expect(result.current.error).toBe('An unknown error occurred.');
  });

  it('requires terms acceptance before adding a phone', async () => {
    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setAddPhoneNumber('5551234567');
      result.current.setAddTermsAccepted(false);
    });
    await act(async () => {
      await result.current.handleAddSubmit(formEvent());
    });

    expect(result.current.addError).toBe('Please accept the Privacy/Legal Notice and Privacy Statement to continue.');
    expect(mocks.createContactPhone).not.toHaveBeenCalled();
  });

  it('surfaces an SMS send failure after the phone is created', async () => {
    mocks.createContactPhone.mockResolvedValue(phone({verified: false}));
    mocks.requestContactPhoneVerification.mockRejectedValue(new Error('sms down'));

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setAddPhoneNumber('5551234567');
      result.current.setAddTermsAccepted(true);
      result.current.setAddSubscribe(true);
    });
    await act(async () => {
      await result.current.handleAddSubmit(formEvent());
    });

    expect(mocks.createContactPhone).toHaveBeenCalledWith({
      phone_number: '5551234567',
      region: '1-US',
      subscribe: true,
    });
    expect(result.current.error).toBe('SMS could not be sent. Tap Resend Code.');
  });

  it('surfaces an add error when creating the phone fails', async () => {
    mocks.createContactPhone.mockRejectedValue(new Error('create failed'));

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setAddPhoneNumber('5551234567');
      result.current.setAddTermsAccepted(true);
    });
    await act(async () => {
      await result.current.handleAddSubmit(formEvent());
    });

    expect(result.current.addError).toBe('An unknown error occurred.');
  });

  it('surfaces a generic error when opening verification fails', async () => {
    mocks.requestContactPhoneVerification.mockRejectedValue(new Error('boom'));

    const {result} = renderHook(() => usePhoneCenter());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleToggleVerify('p-1');
    });

    expect(result.current.error).toBe('An unknown error occurred.');
  });
});
