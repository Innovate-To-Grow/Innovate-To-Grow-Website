import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('./client', () => ({
  default: {
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
} from './contacts';

describe('contacts API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

    it('requestContactPhoneVerification posts to verify endpoint', async () => {
      mocks.post.mockResolvedValue({data: {message: 'sent'}});
      const result = await requestContactPhoneVerification('phone-id');
      expect(mocks.post).toHaveBeenCalledWith('/authn/contact-phones/phone-id/request-verification/');
      expect(result.message).toBe('sent');
    });

    it('verifyContactPhoneCode posts code', async () => {
      mocks.post.mockResolvedValue({data: {id: 'p1', verified: true}});
      const result = await verifyContactPhoneCode('p1', '123456');
      expect(mocks.post).toHaveBeenCalledWith('/authn/contact-phones/p1/verify-code/', {code: '123456'});
      expect(result.verified).toBe(true);
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
      expect(mocks.post).toHaveBeenCalledWith('/authn/contact-emails/', email);
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
      expect(mocks.post).toHaveBeenCalledWith('/authn/contact-emails/e1/request-verification/');
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
