export const profileData = {
  member_uuid: 'uuid-1',
  email: 'member@example.com',
  email_verified: true,
  primary_email_id: 'eid-1',
  first_name: 'Ada',
  middle_name: '',
  last_name: 'Lovelace',
  organization: 'Individual',
  title: '',
  email_subscribe: false,
  is_staff: false,
  is_active: true,
  date_joined: '2026-01-01',
};

export const emailSignIn = () => ({
  access: 'jwt',
  refresh: 'jwt-r',
  user: {member_uuid: 'uuid-1', email: 'test@example.com'},
  requires_profile_completion: true,
});

export const phoneSignIn = () => ({
  access: 'jwt',
  refresh: 'jwt-r',
  user: {member_uuid: 'uuid-1', phone: '+12025550123'},
  requires_profile_completion: false,
});
