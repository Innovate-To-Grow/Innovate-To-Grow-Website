import {VerificationFlowError} from './errors';

let loadPromise: Promise<void> | null = null;

declare global {
  interface Window {
    $altcha?: {
      algorithms: {set: (name: string, factory: () => Worker) => void};
    };
  }
}

export async function loadAltcha(): Promise<void> {
  if (loadPromise) return loadPromise;
  loadPromise = (async () => {
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      const [{default: Pbkdf2Worker}] = await Promise.race([
        Promise.all([import('altcha/workers/pbkdf2?worker'), import('altcha/external')]),
        new Promise<never>((_resolve, reject) => {
          timeout = setTimeout(() => reject(new VerificationFlowError('Unable to load verification assets. Please reload and try again.')), 15_000);
        }),
      ]);
      if (!window.$altcha) throw new VerificationFlowError('Unable to load verification assets.');
      window.$altcha.algorithms.set('PBKDF2/SHA-256', () => new Pbkdf2Worker());
      window.$altcha.algorithms.set('PBKDF2/SHA-384', () => new Pbkdf2Worker());
      window.$altcha.algorithms.set('PBKDF2/SHA-512', () => new Pbkdf2Worker());
    } finally {
      clearTimeout(timeout);
    }
  })().catch((error: unknown) => {
    loadPromise = null;
    throw error;
  });
  return loadPromise;
}
