import {describe, it, expect} from 'vitest';

describe('Component barrel exports', () => {
  it('components/Auth exports resolve', async () => {
    const mod = await import('../components/Auth');
    expect(mod.AuthProvider).toBeDefined();
    expect(mod.useAuth).toBeDefined();
    expect(mod.CodeInput).toBeDefined();
    expect(mod.LoginForm).toBeDefined();
    expect(mod.RegisterForm).toBeDefined();
    expect(mod.AccountPage).toBeDefined();
    expect(mod.CompleteProfilePage).toBeDefined();
    expect(mod.ForgotPasswordPage).toBeDefined();
    expect(mod.LoginPage).toBeDefined();
    expect(mod.RegisterPage).toBeDefined();
    expect(mod.VerifyEmailPage).toBeDefined();
  });

  it('components/CMS exports resolve', async () => {
    const mod = await import('../components/CMS');
    expect(mod.CMSPageComponent).toBeDefined();
    expect(mod.BlockRenderer).toBeDefined();
    expect(mod.useCMSPage).toBeDefined();
  });

  it('components/Layout exports resolve', async () => {
    const mod = await import('../components/Layout');
    expect(mod.Footer).toBeDefined();
    expect(mod.MainMenu).toBeDefined();
    expect(mod.Container).toBeDefined();
    expect(mod.Layout).toBeDefined();
    expect(mod.LayoutProvider).toBeDefined();
    expect(mod.useLayout).toBeDefined();
    expect(mod.useMenu).toBeDefined();
    expect(mod.useFooter).toBeDefined();
  });

  it('components/MaintenanceMode exports resolve', async () => {
    const mod = await import('../components/MaintenanceMode');
    expect(mod.MaintenanceMode).toBeDefined();
    expect(mod.HealthCheckProvider).toBeDefined();
    expect(mod.useHealthCheck).toBeDefined();
  });

  it('components/Projects exports resolve', async () => {
    const mod = await import('../components/Projects');
    expect(mod.MergedResultsTable).toBeDefined();
    expect(mod.PastProjectsBuilder).toBeDefined();
    expect(mod.ProjectGridTable).toBeDefined();
    expect(mod.useProjectGridTable).toBeDefined();
    expect(mod.CURRENT_PROJECT_GRID_COLUMNS).toBeDefined();
    expect(mod.PAST_PROJECT_GRID_COLUMNS).toBeDefined();
    expect(mod.PROJECT_GRID_COLUMNS).toBeDefined();
    expect(mod.createProjectGridFingerprint).toBeDefined();
    expect(mod.createProjectGridItems).toBeDefined();
    expect(mod.stripProjectGridItem).toBeDefined();
  });

  it('components/ScheduleGrid exports resolve', async () => {
    const mod = await import('../components/ScheduleGrid');
    expect(mod.ScheduleGrid).toBeDefined();
  });

  it('components/SheetsDataTable exports resolve', async () => {
    const mod = await import('../components/SheetsDataTable');
    expect(mod.SheetsDataTable).toBeDefined();
  });
});

describe('Page barrel exports', () => {
  const pages = [
    ['AcknowledgementPage', 'AcknowledgementPage'],
    ['EventArchivePage', 'EventArchivePage'],
    ['EventRegistrationPage', 'EventRegistrationPage'],
    ['HomePage', 'HomePage'],
    ['NewsDetailPage', 'NewsDetailPage'],
    ['NewsPage', 'NewsPage'],
    ['NotFoundPage', 'NotFoundPage'],
    ['PastProjectsPage', 'PastProjectsPage'],
    ['ProjectDetailPage', 'ProjectDetailPage'],
    ['ProjectsPage', 'ProjectsPage'],
    ['SchedulePage', 'SchedulePage'],
    ['SubscribePage', 'SubscribePage'],
    ['TicketLoginPage', 'TicketLoginPage'],
    ['UnsubscribeLoginPage', 'UnsubscribeLoginPage'],
  ] as const;

  it.each(pages)('pages/%s exports %s', async (dir, exportName) => {
    const mod = await import(`../pages/${dir}/index.ts`);
    expect(mod[exportName]).toBeDefined();
  });
});
