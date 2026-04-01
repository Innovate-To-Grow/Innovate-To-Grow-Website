import {describe, it, expect} from 'vitest';

describe('CSS imports resolve', () => {
  it('main entry CSS resolves', async () => {
    await expect(import('../index.css')).resolves.toBeDefined();
  });

  const componentsWithCSS = [
    ['Layout/Container', () => import('../components/Layout/Container/Container')],
    ['Layout/MainMenu', () => import('../components/Layout/MainMenu/MainMenu')],
    ['Layout/Footer', () => import('../components/Layout/Footer/Footer')],
    ['CMS/CMSPageComponent', () => import('../components/CMS/CMSPageComponent')],
    ['ScheduleGrid', () => import('../components/ScheduleGrid/ScheduleGrid')],
    ['SheetsDataTable', () => import('../components/SheetsDataTable/SheetsDataTable')],
    ['MaintenanceMode', () => import('../components/MaintenanceMode/MaintenanceMode')],
    ['HealthCheckProvider', () => import('../components/MaintenanceMode/HealthCheckProvider')],
  ] as const;

  it.each(componentsWithCSS)('%s CSS import resolves', async (_name, importFn) => {
    await expect(importFn()).resolves.toBeDefined();
  });
});
