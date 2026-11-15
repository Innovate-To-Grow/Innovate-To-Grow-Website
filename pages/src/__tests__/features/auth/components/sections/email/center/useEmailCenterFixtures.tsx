import type {ContactEmail, ProfileResponse} from '@/features/auth/api';

export const baseProfile = (overrides: Partial<ProfileResponse> = {}): ProfileResponse => ({
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

export const contactEmail = (overrides: Partial<ContactEmail> = {}): ContactEmail => ({
  id: 'e-1',
  email_address: 'secondary@example.com',
  email_type: 'secondary',
  subscribe: true,
  verified: true,
  created_at: '2026-01-02T00:00:00Z',
  ...overrides,
});
