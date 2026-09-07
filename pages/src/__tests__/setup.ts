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
