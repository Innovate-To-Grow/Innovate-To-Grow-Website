import {describe, it, expect} from 'vitest';

describe('CSS imports resolve', () => {
  it('main entry CSS resolves', async () => {
    await expect(import('../index.css')).resolves.toBeDefined();
  });

  const componentsWithCSS = [
    ['Layout/Container', () => import('../components/Layout/Container/Container')],
    ['Layout/MainMenu', () => import('../components/Layout/MainMenu/MainMenu')],
    ['Layout/Footer', () => import('../components/Layout/Footer/Footer')],
    ['CMS/CMSPageComponent', () => import('@/features/cms/components/CMSPageComponent')],
    ['ScheduleGrid', () => import('../components/ScheduleGrid/ScheduleGrid')],
    ['SheetsDataTable', () => import('@/components/ui/SheetsDataTable/SheetsDataTable')],
    ['MaintenanceMode', () => import('@/app/MaintenanceMode/MaintenanceMode')],
    ['HealthCheckProvider', () => import('@/app/MaintenanceMode/HealthCheckProvider')],
  ] as const;

  it.each(componentsWithCSS)('%s CSS import resolves', async (_name, importFn) => {
    await expect(importFn()).resolves.toBeDefined();
  });
});
