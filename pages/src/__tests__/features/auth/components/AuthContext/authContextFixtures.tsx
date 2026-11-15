export const user = {
  member_uuid: '978b882b-d693-4e5e-aee1-21ff69ac82a4',
  email: 'member@example.com',
};
export const session = {
  version: 1 as const,
  access: 'access-1',
  refresh: 'refresh-1',
  user,
  generation: 'generation-1',
  requires_profile_completion: true,
};

export const verifiedSession = {status: 'verified' as const, session};
export const anonymousSession = {status: 'anonymous' as const, session: null};
type BootstrapResult = typeof anonymousSession | {status: 'verified' | 'unverified'; session: typeof session};
export const deferredBootstrap = () => {
  let resolve!: (result: BootstrapResult) => void;
  const promise = new Promise<BootstrapResult>((done) => { resolve = done; });
  return {promise, resolve};
};
export const storageEvent = (key: string | null, storageArea = localStorage) => {
  const event = new StorageEvent('storage', {key});
  Object.defineProperty(event, 'storageArea', {value: storageArea});
  return event;
};
export const authStorageEvent = () => storageEvent('i2g_auth_session');
