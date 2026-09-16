import {beforeEach, expect, it, vi} from 'vitest';

const worker = vi.hoisted(() => vi.fn(function WorkerStub() { return {}; }));
vi.mock('altcha/workers/pbkdf2?worker', () => ({default: worker}));
vi.mock('altcha/external', () => ({}));

beforeEach(() => {
  vi.resetModules();
  worker.mockClear();
  Reflect.deleteProperty(window, '$altcha');
});

it('registers local workers once for concurrent verification requests', async () => {
  const factories = new Map<string, () => Worker>();
  Object.defineProperty(window, '$altcha', {value: {algorithms: factories}, configurable: true});
  const {loadAltcha} = await import('@/features/auth/verification/loadAltcha');
  await Promise.all([loadAltcha(), loadAltcha()]);
  expect([...factories.keys()]).toEqual(['PBKDF2/SHA-256', 'PBKDF2/SHA-384', 'PBKDF2/SHA-512']);
  factories.get('PBKDF2/SHA-256')!();
  expect(worker).toHaveBeenCalledTimes(1);
});

it('allows another attempt after the widget bundle fails to initialize', async () => {
  const {loadAltcha} = await import('@/features/auth/verification/loadAltcha');
  await expect(loadAltcha()).rejects.toThrow('Unable to load verification assets');
  const factories = new Map<string, () => Worker>();
  Object.defineProperty(window, '$altcha', {value: {algorithms: factories}, configurable: true});
  await expect(loadAltcha()).resolves.toBeUndefined();
  expect(factories.has('PBKDF2/SHA-256')).toBe(true);
});
