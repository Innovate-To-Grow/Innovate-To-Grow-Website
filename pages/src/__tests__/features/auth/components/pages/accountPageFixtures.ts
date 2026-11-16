import type {ProfileResponse} from '@/features/auth/api';

export const profile = (): ProfileResponse => ({
  member_uuid: 'm-1',
  email: 'ada@example.com',
  email_verified: true,
  primary_email_id: 'pe-1',
  first_name: 'Ada',
  middle_name: '',
  last_name: 'Lovelace',
  organization: 'Acme Corp',
  title: 'CEO',
  email_subscribe: true,
  is_staff: false,
  is_active: true,
  date_joined: '2026-01-01T00:00:00Z',
});
