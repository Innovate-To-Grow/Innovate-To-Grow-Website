import {describe, it, expect} from 'vitest';

describe('Lazy route modules resolve', () => {
  const authPages = [
    ['LoginPage', () => import('@/features/auth/components/pages/LoginPage')],
    ['RegisterPage', () => import('@/features/auth/components/pages/RegisterPage')],
    ['AccountPage', () => import('@/features/auth/components/pages/AccountPage')],
    ['CompleteProfilePage', () => import('@/features/auth/components/pages/CompleteProfilePage')],
    ['ForgotPasswordPage', () => import('@/features/auth/components/pages/ForgotPasswordPage')],
    ['VerifyEmailPage', () => import('@/features/auth/components/pages/VerifyEmailPage')],
  ] as const;

  const contentPages = [
    ['NewsPage', () => import('@/routes/NewsPage')],
    ['NewsDetailPage', () => import('@/routes/NewsDetailPage')],
    ['ProjectsPage', () => import('@/routes/ProjectsPage')],
    ['PastProjectsPage', () => import('@/routes/PastProjectsPage')],
    ['PresentingTeamsPage', () => import('@/routes/PresentingTeamsPage')],
    ['ProjectDetailPage', () => import('@/routes/ProjectDetailPage')],
    ['SchedulePage', () => import('@/routes/SchedulePage')],
    ['AcknowledgementPage', () => import('@/routes/AcknowledgementPage')],
    ['EventRegistrationPage', () => import('@/routes/EventRegistrationPage')],
    ['TicketLoginPage', () => import('@/routes/TicketLoginPage')],
    ['SubscribePage', () => import('@/routes/SubscribePage')],
    ['UnsubscribeLoginPage', () => import('@/routes/UnsubscribeLoginPage')],
  ] as const;

  it.each([...authPages, ...contentPages])(
    '%s module resolves and has named export',
    async (exportName, importFn) => {
      const mod = await importFn();
      expect(mod).toHaveProperty(exportName as string);
      expect((mod as Record<string, unknown>)[exportName as string]).toBeDefined();
    },
  );
});
