import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {FormEvent} from 'react';

import type {ContactPhone} from '@/features/auth/api';
import {usePhoneCenter} from '@/features/auth/components/sections/internal/usePhoneCenter';

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

    expect(result.current.addError).toBe('Please accept Terms of Service & Privacy Policy to continue.');
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

    expect(result.current.verifyError).toBe('Please accept Terms of Service & Privacy Policy to continue.');
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

  it('resets the form when submitting without a phone number', async () => {
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

    expect(result.current.showAddForm).toBe(false);
    expect(result.current.addSubscribe).toBe(false);
    expect(result.current.addTermsAccepted).toBe(false);
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
