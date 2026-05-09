import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  updateStoredUser: vi.fn(),
}));

vi.mock('./client', () => ({
  authApi: {
    get: mocks.get,
    patch: mocks.patch,
  },
}));

vi.mock('./storage', () => ({
  updateStoredUser: mocks.updateStoredUser,
}));

import {getAccountEmails, getProfile, updateProfileFields, uploadProfileImage} from './profile';

describe('profile API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getProfile', () => {
    it('fetches profile from /authn/profile/', async () => {
      const profileData = {first_name: 'Alice', last_name: 'Smith', email: 'a@b.com'};
      mocks.get.mockResolvedValue({data: profileData});

      const result = await getProfile();
      expect(mocks.get).toHaveBeenCalledWith('/authn/profile/');
      expect(result).toEqual(profileData);
    });
  });

  describe('updateProfileFields', () => {
    it('patches profile with fields', async () => {
      const updated = {first_name: 'Bob'};
      mocks.patch.mockResolvedValue({data: {first_name: 'Bob', last_name: 'Smith'}});

      const result = await updateProfileFields(updated);
      expect(mocks.patch).toHaveBeenCalledWith('/authn/profile/', updated);
      expect(result.first_name).toBe('Bob');
    });
  });

  describe('uploadProfileImage', () => {
    it('sends FormData and updates stored user', async () => {
      const file = new File(['img-data'], 'photo.png', {type: 'image/png'});
      const responseData = {profile_image: '/media/photo.png', first_name: 'X', last_name: 'Y'};
      mocks.patch.mockResolvedValue({data: responseData});

      const result = await uploadProfileImage(file);

      expect(mocks.patch).toHaveBeenCalledWith('/authn/profile/', expect.any(FormData));
      expect(mocks.updateStoredUser).toHaveBeenCalled();
      expect(result.profile_image).toBe('/media/photo.png');
    });
  });

  describe('getAccountEmails', () => {
    it('fetches account emails', async () => {
      mocks.get.mockResolvedValue({data: {emails: [{id: '1', email_address: 'x@y.com'}]}});

      const result = await getAccountEmails();
      expect(mocks.get).toHaveBeenCalledWith('/authn/account-emails/');
      expect(result.emails).toHaveLength(1);
    });
  });
});
