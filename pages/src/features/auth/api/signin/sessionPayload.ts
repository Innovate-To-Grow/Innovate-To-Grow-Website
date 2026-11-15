import type {User} from '../contracts/types';

export type SessionPayload = Record<string, unknown> & {
  authenticated?: boolean;
  user?: unknown;
  profile?: unknown;
  requires_profile_completion?: unknown;
};

const asObject = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : null;

const readString = (
  candidate: Record<string, unknown>,
  key: string,
  fallback: string,
) => {
  const value = candidate[key];
  return typeof value === 'string' ? value : fallback;
};

const readOptionalString = (
  candidate: Record<string, unknown>,
  key: string,
  fallback: string | undefined,
) => {
  if (!(key in candidate)) return fallback;
  const value = candidate[key];
  return typeof value === 'string' ? value : undefined;
};

const readSessionUser = (
  candidate: Record<string, unknown>,
  memberUuid: string,
  fallback: User,
): User => ({
  ...fallback,
  member_uuid: memberUuid,
  email: readString(candidate, 'email', fallback.email),
  phone: readOptionalString(candidate, 'phone', fallback.phone),
  profile_image: readOptionalString(
    candidate,
    'profile_image',
    fallback.profile_image,
  ),
  is_staff:
    typeof candidate.is_staff === 'boolean'
      ? candidate.is_staff
      : fallback.is_staff,
  first_name: readOptionalString(candidate, 'first_name', fallback.first_name),
  last_name: readOptionalString(candidate, 'last_name', fallback.last_name),
});

/**
 * The explicit flag (top-level, then on the user), else derived from the
 * profile fields the payload carries; undefined when it carries neither, so
 * the stored flag is kept.
 */
const readRequiresProfileCompletion = (
  payload: SessionPayload,
  candidate: Record<string, unknown>,
): boolean | undefined => {
  if (typeof payload.requires_profile_completion === 'boolean')
    return payload.requires_profile_completion;
  const nestedRequires = candidate.requires_profile_completion;
  if (typeof nestedRequires === 'boolean') return nestedRequires;
  if (
    !(
      'first_name' in candidate ||
      'last_name' in candidate ||
      'organization' in candidate
    )
  )
    return undefined;
  return !(
    readString(candidate, 'first_name', '').trim() &&
    readString(candidate, 'last_name', '').trim() &&
    readString(candidate, 'organization', '').trim()
  );
};

export const normalizeSessionUser = (
  payload: SessionPayload,
  fallback: User,
  fallbackRequiresProfileCompletion: boolean,
): {user: User; requiresProfileCompletion: boolean} | null => {
  const candidate =
    asObject(payload.user) ?? asObject(payload.profile) ?? asObject(payload);
  if (!candidate) return null;

  const memberUuid = readString(candidate, 'member_uuid', fallback.member_uuid);
  if (!memberUuid) return null;

  return {
    user: readSessionUser(candidate, memberUuid, fallback),
    requiresProfileCompletion:
      readRequiresProfileCompletion(payload, candidate) ??
      fallbackRequiresProfileCompletion,
  };
};
