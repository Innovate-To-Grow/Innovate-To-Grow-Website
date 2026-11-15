export const baseSession = {
  version: 1 as const,
  generation: 'generation-a',
  access: 'access-token',
  refresh: 'refresh-token',
  user: {
    member_uuid: 'member-a',
    email: 'old@example.com',
    is_staff: false,
  },
  requires_profile_completion: false,
};
