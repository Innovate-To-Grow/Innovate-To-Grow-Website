/* eslint-disable react-hooks/rules-of-hooks -- Playwright's fixture `use` callback is not a React hook. */
// Mocked specs import `test`/`expect` from here. The `page` fixture is wrapped
// so every mocked test gets `mockHealthyAppShell` applied automatically (no
// per-test boilerplate). The live smoke spec uses `@playwright/test` directly.
import {test as base, expect} from '@playwright/test';
import {mockHealthyAppShell} from './helpers/shell';

export const test = base.extend({
  page: async ({page}, use) => {
    await mockHealthyAppShell(page);
    await use(page);
  },
});

export {expect};
