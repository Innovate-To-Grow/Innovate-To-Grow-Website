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
    ['NewsPage', () => import('@/routes/news/NewsPage')],
    ['NewsDetailPage', () => import('@/routes/news/NewsDetailPage')],
    ['ProjectsPage', () => import('@/routes/projects/ProjectsPage')],
    ['PastProjectsPage', () => import('@/routes/projects/PastProjectsPage')],
    ['AllProjectsPage', () => import('@/routes/projects/AllProjectsPage')],
    ['PresentingTeamsPage', () => import('@/routes/projects/PresentingTeamsPage')],
    ['ProjectDetailPage', () => import('@/routes/projects/ProjectDetailPage')],
    ['SchedulePage', () => import('@/routes/events/SchedulePage/page')],
    ['AcknowledgementPage', () => import('@/routes/events/AcknowledgementPage')],
    ['EventArchivePage', () => import('@/routes/events/EventArchivePage')],
    ['EventRegistrationPage', () => import('@/routes/events/EventRegistrationPage/page')],
    ['LoginLinkPage', () => import('@/routes/auth/LoginLinkPage')],
    ['SubscribePage', () => import('@/routes/subscription/SubscribePage/page')],
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
