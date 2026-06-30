import {describe, it, expect} from 'vitest';

describe('CSS imports resolve', () => {
  it('main entry CSS resolves', async () => {
    await expect(import('../index.css')).resolves.toBeDefined();
  });

  const componentsWithCSS = [
    ['Layout/Container', () => import('@/features/layout/components/Container/Container')],
    ['Layout/MainMenu', () => import('@/features/layout/components/MainMenu/MainMenu')],
    ['Layout/Footer', () => import('@/features/layout/components/Footer/Footer')],
    ['CMS/CMSPageComponent', () => import('@/features/cms/components/CMSPageComponent')],
    ['ScheduleGrid', () => import('@/features/events/components/ScheduleGrid/ScheduleGrid')],
    ['SheetsDataTable', () => import('@/components/ui/SheetsDataTable/SheetsDataTable')],
    ['MaintenanceMode', () => import('@/app/MaintenanceMode/MaintenanceMode')],
    ['HealthCheckProvider', () => import('@/app/MaintenanceMode/HealthCheckProvider')],
    ['Projects components', () => import('@/features/projects/components')],
    ['AccountPage', () => import('@/features/auth/components/pages/AccountPage')],
    [
      'PastProjectCurationSharedLinksPage',
      () => import('@/features/auth/components/pages/PastProjectCurationSharedLinksPage'),
    ],
  ] as const;

  it.each(componentsWithCSS)('%s CSS import resolves', async (_name, importFn) => {
    await expect(importFn()).resolves.toBeDefined();
  });
});
