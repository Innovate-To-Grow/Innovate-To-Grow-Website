import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {FormEvent} from 'react';

import type {ContactEmail, ProfileResponse} from '@/features/auth/api';
import {useEmailCenter} from '@/features/auth/components/sections/internal/useEmailCenter';

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

const baseProfile = (overrides: Partial<ProfileResponse> = {}): ProfileResponse => ({
  member_uuid: 'm-1',
  email: 'primary@example.com',
  email_verified: false,
  primary_email_id: 'pe-1',
  first_name: 'Pat',
  middle_name: '',
  last_name: 'Person',
  organization: '',
  title: '',
  email_subscribe: true,
  is_staff: false,
  is_active: true,
  date_joined: '2026-01-01T00:00:00Z',
  ...overrides,
});

const contactEmail = (overrides: Partial<ContactEmail> = {}): ContactEmail => ({
  id: 'e-1',
  email_address: 'secondary@example.com',
  email_type: 'secondary',
  subscribe: true,
  verified: true,
  created_at: '2026-01-02T00:00:00Z',
  ...overrides,
});

const formEvent = () => ({preventDefault: vi.fn()}) as unknown as FormEvent;

describe('useEmailCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getContactEmails.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it('loads contact emails and stops loading', async () => {
    mocks.getContactEmails.mockResolvedValue([contactEmail()]);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.contactEmails).toEqual([contactEmail()]);
  });

  it('stays empty and silent when the initial fetch fails', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    mocks.getContactEmails.mockRejectedValue(new Error('boom'));

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.contactEmails).toEqual([]);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it('toggles the primary subscription and reports success', async () => {
    const onProfileUpdate = vi.fn();
    mocks.updateProfileFields.mockResolvedValue(baseProfile({email_subscribe: false}));

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimarySubscribeToggle();
    });

    expect(mocks.updateProfileFields).toHaveBeenCalledWith({email_subscribe: false});
    expect(onProfileUpdate).toHaveBeenCalledWith(baseProfile({email_subscribe: false}));
    expect(result.current.successMessage).toBe('Primary email unsubscribed.');
  });

  it('surfaces an error when the primary subscribe toggle fails', async () => {
    mocks.updateProfileFields.mockRejectedValue({response: {data: {detail: 'Subscribe failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handlePrimarySubscribeToggle();
    });

    expect(result.current.error).toBe('Subscribe failed');
  });

  it('toggles a contact subscription', async () => {
    mocks.getContactEmails.mockResolvedValue([contactEmail()]);
    const updated = contactEmail({subscribe: false});
    mocks.updateContactEmail.mockResolvedValue(updated);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleContactSubscribeToggle(contactEmail());
    });

    expect(mocks.updateContactEmail).toHaveBeenCalledWith('e-1', {subscribe: false});
    expect(result.current.contactEmails).toEqual([updated]);
  });

  it('surfaces an error when a contact subscribe toggle fails', async () => {
    mocks.updateContactEmail.mockRejectedValue({response: {data: {detail: 'Toggle failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleContactSubscribeToggle(contactEmail());
    });

    expect(result.current.error).toBe('Toggle failed');
  });

  it('rejects changing an email to secondary when one already exists', async () => {
    mocks.getContactEmails.mockResolvedValue([
      contactEmail({id: 'e-1', email_type: 'secondary'}),
      contactEmail({id: 'e-2', email_address: 'other@example.com', email_type: 'other'}),
    ]);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    const second = contactEmail({id: 'e-2', email_address: 'other@example.com', email_type: 'other'});
    await act(async () => {
      await result.current.handleContactTypeChange(second, 'secondary');
    });

    expect(mocks.updateContactEmail).not.toHaveBeenCalled();
    expect(result.current.error).toBe('You already have a secondary email.');
  });

  it('changes a contact email type', async () => {
    mocks.getContactEmails.mockResolvedValue([contactEmail()]);
    const updated = contactEmail({email_type: 'other'});
    mocks.updateContactEmail.mockResolvedValue(updated);

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleContactTypeChange(contactEmail(), 'other');
    });

    expect(mocks.updateContactEmail).toHaveBeenCalledWith('e-1', {email_type: 'other'});
    expect(result.current.contactEmails).toEqual([updated]);
  });

  it('surfaces an error when a contact type change fails', async () => {
    mocks.updateContactEmail.mockRejectedValue({response: {data: {detail: 'Type failed'}}});

    const {result} = renderHook(() =>
      useEmailCenter({profile: baseProfile(), onProfileUpdate: vi.fn()}),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.handleContactTypeChange(contactEmail(), 'other');
    });

    expect(result.current.error).toBe('Type failed');
  });

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

    expect(mocks.makeContactEmailPrimary).toHaveBeenCalledWith('e-1');
    expect(mocks.getProfile).toHaveBeenCalled();
    expect(mocks.getContactEmails).toHaveBeenCalled();
    expect(result.current.successMessage).toBe(
      'Primary email updated. Your previous primary address is now listed as a connected email.',
    );
  });

  it('surfaces a make-primary error', async () => {
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
