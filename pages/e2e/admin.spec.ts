import {expect, test, type Page} from '@playwright/test';

const apiBaseUrl = process.env.PLAYWRIGHT_API_BASE_URL ?? 'http://127.0.0.1:8000';
const adminEmail = process.env.ADMIN_E2E_EMAIL ?? 'admin-e2e@example.com';
const adminPassword = process.env.ADMIN_E2E_PASSWORD ?? 'admin-e2e-password';
const nonstaffEmail = process.env.ADMIN_E2E_NONSTAFF_EMAIL ?? 'admin-e2e-nonstaff@example.com';
const actionEmail = process.env.ADMIN_E2E_ACTION_EMAIL ?? 'action-e2e@example.com';
const seededProjectTitle = 'E2E Solar Orchard Dashboard';
const seededSemesterLabel = '2099-2 Fall';
const themeRuntimeErrorPattern =
  /theme is not defined|adminTheme is not defined|themeBindings is not defined|openModal is not defined/i;

async function adminLogin(page: Page, email = adminEmail, password = adminPassword) {
  await page.goto(`${apiBaseUrl}/admin/login/?mode=password`, {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.login-title, h1, [role="heading"]').first()).toBeVisible();

  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', {name: /sign in/i}).click();
}

async function expectLoggedInAdmin(page: Page) {
  await expect(page).toHaveURL(/\/admin\/?(?:\?.*)?$/);
  await expect(page.locator('body')).toContainText(/Welcome to I2G Admin|Innovate To Grow Admin|I2G Admin/i);
}

function collectThemeRuntimeErrors(page: Page) {
  const errors: string[] = [];

  page.on('console', (message) => {
    if (!['error', 'warning'].includes(message.type())) return;
    if (themeRuntimeErrorPattern.test(message.text())) errors.push(message.text());
  });

  page.on('pageerror', (error) => {
    if (themeRuntimeErrorPattern.test(error.message)) errors.push(error.message);
  });

  return errors;
}

async function expectAdminDocument(page: Page, path: string) {
  const response = await page.goto(`${apiBaseUrl}${path}`, {waitUntil: 'domcontentloaded'});
  expect(response, `${path} returned a response`).not.toBeNull();
  expect(response?.status(), `${path} should load successfully`).toBeLessThan(400);
  await expect(page.locator('body')).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/Traceback|Internal Server Error/i);
}

async function runChangelistAction(page: Page, rowText: string, actionValue: string) {
  const row = page.locator('tr', {hasText: rowText}).first();
  await expect(row, `Expected an admin row containing ${rowText}`).toBeVisible();
  await row.locator('input[name="_selected_action"]').check();
  await page.locator('select[name="action"]').selectOption(actionValue);
  await page.getByTitle('Run the selected action').click();

  if (/\/confirm-action\//.test(page.url())) {
    await page.locator('#confirm-input').fill('Contact Email');
    await page.getByRole('button', {name: /confirm action/i}).click();
  }
}

// @admin pins this live, DB-mutating admin suite to the chromium project
// (see playwright.config.ts) — firefox/webkit and the mobile devices skip it.
test.describe.serial('Django admin browser flows', {tag: '@admin'}, () => {
  test('requires authentication before showing the admin index', async ({page}) => {
    await page.goto(`${apiBaseUrl}/admin/`, {waitUntil: 'domcontentloaded'});

    await expect(page).toHaveURL(/\/admin\/login\//);
    await expect(page.getByLabel('Email')).toBeVisible();
  });

  test('rejects invalid admin credentials without entering the dashboard', async ({page}) => {
    await adminLogin(page, adminEmail, 'definitely-not-the-admin-password');

    await expect(page).toHaveURL(/\/admin\/login\//);
    await expect(page.locator('body')).toContainText(/Invalid email or password/i);
    await expect(page.locator('body')).not.toContainText(/Welcome to I2G Admin/i);
  });

  test('blocks a valid non-staff user at the admin password login boundary', async ({page}) => {
    await adminLogin(page, nonstaffEmail, adminPassword);

    await expect(page).toHaveURL(/\/admin\/login\//);
    await expect(page.locator('body')).toContainText(/Invalid email or password/i);
    await expect(page.locator('body')).not.toContainText(/Welcome to I2G Admin/i);
  });

  test('logs in through the deterministic password-mode admin login', async ({page}) => {
    await adminLogin(page);
    await expectLoggedInAdmin(page);
  });

  test('switches and persists the global admin theme without runtime errors', async ({page}) => {
    const themeRuntimeErrors = collectThemeRuntimeErrors(page);

    await page.goto(`${apiBaseUrl}/admin/login/?mode=password`, {waitUntil: 'domcontentloaded'});
    await page.evaluate(() => window.localStorage.removeItem('adminTheme'));
    await page.getByLabel('Email').fill(adminEmail);
    await page.getByLabel('Password').fill(adminPassword);
    await page.getByRole('button', {name: /sign in/i}).click();
    await expectLoggedInAdmin(page);

    const themeToggle = page.getByTestId('i2g-admin-theme-toggle');
    await expect(themeToggle).toBeVisible();
    await expect(themeToggle.locator('.i2g-admin-theme-toggle__icon')).not.toHaveText('');
    await expect(themeToggle.locator('.i2g-admin-theme-toggle__text')).toContainText(/Light|Dark|System/);

    await themeToggle.getByRole('button', {name: /switch admin theme/i}).click();
    const darkThemeChoice = themeToggle.locator('[data-admin-theme-choice="dark"]');
    await expect(darkThemeChoice).toBeVisible();
    await darkThemeChoice.click();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)dark(?:\s|$)/);

    await page.reload({waitUntil: 'domcontentloaded'});
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)dark(?:\s|$)/);
    expect(themeRuntimeErrors).toEqual([]);
  });

  test('loads the admin index and critical custom changelists', async ({page}) => {
    await adminLogin(page);
    await expectLoggedInAdmin(page);

    const adminPaths = [
      '/admin/authn/member/',
      '/admin/authn/contactemail/',
      '/admin/projects/project/',
      '/admin/projects/semester/',
      '/admin/cms/cmspage/',
      '/admin/event/event/',
      '/admin/mail/emailcampaign/',
      '/admin/system_intelligence/systemintelligenceconfig/',
    ];

    for (const path of adminPaths) {
      await expectAdminDocument(page, path);
    }
  });

  test('loads project changelist and exercises admin search', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/projects/project/');

    await expect(page.locator('body')).toContainText(seededProjectTitle);
    await page.locator('input[name="q"]').fill('Solar Orchard');
    await page.locator('input[name="q"]').press('Enter');

    await expect(page).toHaveURL(/\/admin\/projects\/project\/\?q=Solar\+Orchard/);
    await expect(page.locator('body')).toContainText(seededProjectTitle);
    await expect(page.locator('body')).not.toContainText(/0 projects|0 results/i);
  });

  test('applies a project changelist filter from querystring-backed admin filters', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/projects/project/?industry=Testing');

    await expect(page.locator('body')).toContainText(seededProjectTitle);
    await expect(page.locator('body')).toContainText('Testing');
  });

  test('changes an existing project through the admin change form', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/projects/project/');

    await page.locator('input[name="q"]').fill(seededProjectTitle);
    await page.locator('input[name="q"]').press('Enter');
    await page.getByRole('link', {name: seededProjectTitle}).first().click();

    const updatedOrganization = `Innovate To Grow QA Updated ${Date.now()}`;
    await expect(page.locator('input[name="organization"]')).toBeVisible();
    await page.locator('input[name="organization"]').fill(updatedOrganization);
    await page.locator('button[name="_save"]').click();

    await expect(page).toHaveURL(/\/admin\/projects\/project\//);
    await expect(page.locator('body')).toContainText(/was changed successfully|changed successfully/i);

    await page.locator('input[name="q"]').fill(updatedOrganization);
    await page.locator('input[name="q"]').press('Enter');
    await expect(page.locator('body')).toContainText(seededProjectTitle);
    await expect(page.locator('body')).toContainText(updatedOrganization);
  });

  test('adds a project through the admin change form', async ({page}) => {
    await adminLogin(page);

    const projectTitle = `E2E Browser Added Project ${Date.now()}`;
    await expectAdminDocument(page, '/admin/projects/project/add/');

    await page.locator('select[name="semester"]').selectOption({label: seededSemesterLabel});
    await page.locator('input[name="class_code"]').fill('E2E');
    await page.locator('input[name="team_number"]').fill(`PW-${Date.now().toString().slice(-6)}`);
    await page.locator('input[name="team_name"]').fill('Playwright Admin Team');
    await page.locator('input[name="project_title"]').fill(projectTitle);
    await page.locator('input[name="organization"]').fill('Innovate To Grow QA');
    await page.locator('input[name="industry"]').fill('Testing');
    await page.locator('textarea[name="abstract"]').fill('Created by the Django admin Playwright E2E test.');
    await page.locator('textarea[name="student_names"]').fill('Katherine Johnson; Dorothy Vaughan');

    await page.locator('button[name="_save"]').click();

    await expect(page).toHaveURL(/\/admin\/projects\/project\//);
    await expect(page.locator('body')).toContainText(/was added successfully|added successfully/i);

    await page.locator('input[name="q"]').fill(projectTitle);
    await page.locator('input[name="q"]').press('Enter');
    await expect(page.locator('body')).toContainText(projectTitle);
  });

  test('runs a dry-run project CSV import through the custom admin view', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/projects/semester/import-csv/');

    const csv = [
      'Year-Semester,ClassCode,Team#,TeamName,ProjectTitle,Organization,Industry,Col7,Abstract,StudentNames',
      '2098-2 Fall,E2E,DRY-1,Dry Run Team,E2E Dry Run Import Project,QA Org,Testing,,Dry run abstract,Ada Lovelace',
    ].join('\n');

    await page.locator('input[name="csv_file"]').setInputFiles({
      name: 'projects-e2e-dry-run.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(csv),
    });
    await page.locator('input[name="dry_run"]').check();
    await page.getByRole('button', {name: /import/i}).click();

    await expect(page).toHaveURL(/\/admin\/projects\/semester\//);
    await expect(page.locator('body')).toContainText(/\[DRY RUN\].*project\(s\) created/i);
  });

  test('publishes semesters through the custom admin toolbar action', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/projects/semester/');

    await page.locator('#publish-all-confirmation').fill('publish all');
    await page.getByRole('button', {name: /publish all/i}).click();

    await expect(page).toHaveURL(/\/admin\/projects\/semester\//);
    await expect(page.locator('body')).toContainText(/semester\(s\) published/i);
  });

  test('runs contact email bulk actions from the Unfold admin changelist', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/authn/contactemail/');

    await page.locator('input[name="q"]').fill(actionEmail);
    await page.locator('input[name="q"]').press('Enter');
    await expect(page.locator('body')).toContainText(actionEmail);

    await runChangelistAction(page, actionEmail, 'mark_verified');
    await expect(page.locator('body')).toContainText(/1 email\(s\) marked as verified/i);

    await page.locator('input[name="q"]').fill(actionEmail);
    await page.locator('input[name="q"]').press('Enter');
    await runChangelistAction(page, actionEmail, 'toggle_subscribe');
    await expect(page.locator('body')).toContainText(/Toggled subscription for 1 email\(s\)/i);
  });
});
