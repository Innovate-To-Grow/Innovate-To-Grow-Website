import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
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
    // Newsletters are opt-in for a newly added address.
    expect(result.current.addSubscribe).toBe(false);
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
});
