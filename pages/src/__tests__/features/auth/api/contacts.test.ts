import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/features/auth/api/client', () => ({
  authApi: {
    get: mocks.get,
    post: mocks.post,
    patch: mocks.patch,
    delete: mocks.delete,
  },
}));

import {
  createContactEmail,
  createContactPhone,
  deleteContactEmail,
  deleteContactPhone,
  getContactEmails,
  getContactPhones,
  makeContactEmailPrimary,
  requestContactEmailVerification,
  requestContactPhoneVerification,
  updateContactEmail,
  updateContactPhone,
  verifyContactEmailCode,
  verifyContactPhoneCode,
} from '@/features/auth/api/contacts';

describe('contacts API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  describe('phones', () => {
    it('getContactPhones fetches list', async () => {
      mocks.get.mockResolvedValue({data: [{id: '1', phone_number: '1234567890'}]});
      const result = await getContactPhones();
      expect(mocks.get).toHaveBeenCalledWith('/authn/contact-phones/');
      expect(result).toHaveLength(1);
    });

    it('createContactPhone posts data', async () => {
      const phone = {phone_number: '5551234', region: '1-US'};
      mocks.post.mockResolvedValue({data: {id: '2', ...phone}});
      const result = await createContactPhone(phone);
      expect(mocks.post).toHaveBeenCalledWith('/authn/contact-phones/', phone);
      expect(result.id).toBe('2');
    });

    it('updateContactPhone patches subscribe', async () => {
      mocks.patch.mockResolvedValue({data: {id: '1', subscribe: true}});
      await updateContactPhone('1', {subscribe: true});
      expect(mocks.patch).toHaveBeenCalledWith('/authn/contact-phones/1/', {subscribe: true});
    });

    it('deleteContactPhone sends delete', async () => {
      mocks.delete.mockResolvedValue({});
      await deleteContactPhone('1');
      expect(mocks.delete).toHaveBeenCalledWith('/authn/contact-phones/1/');
    });

    it('requestContactPhoneVerification persists the returned challenge', async () => {
      const challengeId = '87f80894-955d-49d7-b5f3-2aed231087b1';
      mocks.post.mockResolvedValue({
        data: {message: 'sent', challenge_id: challengeId},
      });
      const result = await requestContactPhoneVerification('phone-id');
      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/contact-phones/phone-id/request-verification/',
        expect.objectContaining({verification_challenge_id: expect.any(String)}),
      );
      expect(result.message).toBe('sent');
      expect(result.challenge_id).toBe(challengeId);
    });

    it('verifyContactPhoneCode passes the persisted challenge', async () => {
      const challengeId = '87f80894-955d-49d7-b5f3-2aed231087b1';
      mocks.post
        .mockResolvedValueOnce({
          data: {message: 'sent', challenge_id: challengeId},
        })
        .mockResolvedValueOnce({data: {id: 'p1', verified: true}});
      await requestContactPhoneVerification('p1');
      const result = await verifyContactPhoneCode('p1', '123456');
      expect(mocks.post).toHaveBeenLastCalledWith(
        '/authn/contact-phones/p1/verify-code/',
        {code: '123456', challenge_id: challengeId},
      );
      expect(result.verified).toBe(true);
    });

    it('verifyContactPhoneCode keeps the legacy code-only payload', async () => {
      mocks.post.mockResolvedValue({data: {id: 'p1', verified: true}});

      await verifyContactPhoneCode('p1', '123456');

      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/contact-phones/p1/verify-code/',
        {code: '123456'},
      );
    });
  });

  describe('emails', () => {
    it('getContactEmails fetches list', async () => {
      mocks.get.mockResolvedValue({data: [{id: '1', email_address: 'a@b.com'}]});
      const result = await getContactEmails();
      expect(mocks.get).toHaveBeenCalledWith('/authn/contact-emails/');
      expect(result).toHaveLength(1);
    });

    it('createContactEmail posts data', async () => {
      const email = {email_address: 'new@test.com', email_type: 'secondary' as const};
      mocks.post.mockResolvedValue({data: {id: '3', ...email}});
      const result = await createContactEmail(email);
      expect(mocks.post).toHaveBeenCalledWith('/authn/contact-emails/', expect.objectContaining(email));
      expect(result.id).toBe('3');
    });

    it('updateContactEmail patches fields', async () => {
      mocks.patch.mockResolvedValue({data: {id: '1', subscribe: false}});
      await updateContactEmail('1', {subscribe: false});
      expect(mocks.patch).toHaveBeenCalledWith('/authn/contact-emails/1/', {subscribe: false});
    });

    it('deleteContactEmail sends delete', async () => {
      mocks.delete.mockResolvedValue({});
      await deleteContactEmail('e1');
      expect(mocks.delete).toHaveBeenCalledWith('/authn/contact-emails/e1/');
    });

    it('requestContactEmailVerification posts', async () => {
      mocks.post.mockResolvedValue({data: {message: 'sent'}});
      await requestContactEmailVerification('e1');
      expect(mocks.post).toHaveBeenCalledWith(
        '/authn/contact-emails/e1/request-verification/',
        expect.objectContaining({verification_challenge_id: expect.any(String)}),
      );
    });

    it('verifyContactEmailCode posts code', async () => {
      mocks.post.mockResolvedValue({data: {id: 'e1', verified: true}});
      const result = await verifyContactEmailCode('e1', '999');
      expect(mocks.post).toHaveBeenCalledWith('/authn/contact-emails/e1/verify-code/', {code: '999'});
      expect(result.verified).toBe(true);
    });

    it('makeContactEmailPrimary posts', async () => {
      mocks.post.mockResolvedValue({data: {id: 'e1', email_type: 'primary'}});
      const result = await makeContactEmailPrimary('e1');
      expect(mocks.post).toHaveBeenCalledWith('/authn/contact-emails/e1/make-primary/');
      expect(result.email_type).toBe('primary');
    });
  });
});
