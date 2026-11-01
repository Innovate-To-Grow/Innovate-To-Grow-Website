import '@testing-library/jest-dom/vitest';
import {vi} from 'vitest';

vi.mock('@/features/auth/verification', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth/verification')>();
  return {
    ...actual,
    withVerifiedSend: async ({execute}: {execute: (verification: Record<string, string>) => Promise<unknown>}) =>
      execute({
        verification_challenge_id: '11111111-1111-4111-8111-111111111111',
        verification_payload: 'test-altcha-payload',
        send_request_id: '22222222-2222-4222-8222-222222222222',
      }),
  };
});

// A Past Projects search table also asks the archive which projects match, once typing pauses, for the abstracts its
// compact rows leave out. Unit tests that type a search must not send that request from jsdom: the stub answers
// that the server finds nothing more. A test of the server search mocks searchPastProjectArchiveIds itself, and the
// archive client's own test unmocks this module.
vi.mock('@/features/projects/api/archive', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api/archive')>()),
  searchPastProjectArchiveIds: vi.fn(async () => new Set<string>()),
}));
