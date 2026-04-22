import {describe, it, expect} from 'vitest';

describe('Lazy route modules resolve', () => {
  const authPages = [
    ['LoginPage', () => import('../components/Auth/pages/LoginPage')],
    ['RegisterPage', () => import('../components/Auth/pages/RegisterPage')],
    ['AccountPage', () => import('../components/Auth/pages/AccountPage')],
    ['CompleteProfilePage', () => import('../components/Auth/pages/CompleteProfilePage')],
    ['ForgotPasswordPage', () => import('../components/Auth/pages/ForgotPasswordPage')],
    ['VerifyEmailPage', () => import('../components/Auth/pages/VerifyEmailPage')],
  ] as const;

  const contentPages = [
    ['NewsPage', () => import('../pages/NewsPage')],
    ['NewsDetailPage', () => import('../pages/NewsDetailPage')],
    ['ProjectsPage', () => import('../pages/ProjectsPage')],
    ['PastProjectsPage', () => import('../pages/PastProjectsPage')],
    ['PresentingTeamsPage', () => import('../pages/PresentingTeamsPage')],
    ['ProjectDetailPage', () => import('../pages/ProjectDetailPage')],
    ['SchedulePage', () => import('../pages/SchedulePage')],
    ['AcknowledgementPage', () => import('../pages/AcknowledgementPage')],
    ['EventArchivePage', () => import('../pages/EventArchivePage')],
    ['EventRegistrationPage', () => import('../pages/EventRegistrationPage')],
    ['TicketLoginPage', () => import('../pages/TicketLoginPage')],
    ['SubscribePage', () => import('../pages/SubscribePage')],
    ['UnsubscribeLoginPage', () => import('../pages/UnsubscribeLoginPage')],
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
