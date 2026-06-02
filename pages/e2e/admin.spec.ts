import {expect, test, type Page} from '@playwright/test';

const apiBaseUrl = process.env.PLAYWRIGHT_API_BASE_URL ?? 'http://127.0.0.1:8000';
const adminEmail = process.env.ADMIN_E2E_EMAIL ?? 'admin-e2e@example.com';
const adminPassword = process.env.ADMIN_E2E_PASSWORD ?? 'admin-e2e-password';

async function adminLogin(page: Page) {
  await page.goto(`${apiBaseUrl}/admin/login/?mode=password`, {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.login-title, h1, [role="heading"]').first()).toBeVisible();

  await page.getByLabel('Email').fill(adminEmail);
  await page.getByLabel('Password').fill(adminPassword);
  await page.getByRole('button', {name: /sign in/i}).click();

  await expect(page).toHaveURL(/\/admin\/?(?:\?.*)?$/);
  await expect(page.locator('body')).toContainText(/Welcome to I2G Admin|Innovate To Grow Admin|I2G Admin/i);
}

async function expectAdminDocument(page: Page, path: string) {
  const response = await page.goto(`${apiBaseUrl}${path}`, {waitUntil: 'domcontentloaded'});
  expect(response, `${path} returned a response`).not.toBeNull();
  expect(response?.status(), `${path} should load successfully`).toBeLessThan(400);
  await expect(page.locator('body')).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/Traceback|Internal Server Error/i);
}

test.describe.serial('Django admin browser flows', () => {
  test('requires authentication before showing the admin index', async ({page}) => {
    await page.goto(`${apiBaseUrl}/admin/`, {waitUntil: 'domcontentloaded'});

    await expect(page).toHaveURL(/\/admin\/login\//);
    await expect(page.getByLabel('Email')).toBeVisible();
  });

  test('logs in through the deterministic password-mode admin login', async ({page}) => {
    await adminLogin(page);
  });

  test('loads project changelist and exercises admin search', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/projects/project/');

    await expect(page.locator('body')).toContainText('E2E Solar Orchard Dashboard');
    await page.locator('input[name="q"]').fill('Solar Orchard');
    await page.locator('input[name="q"]').press('Enter');

    await expect(page).toHaveURL(/\/admin\/projects\/project\/\?q=Solar\+Orchard/);
    await expect(page.locator('body')).toContainText('E2E Solar Orchard Dashboard');
    await expect(page.locator('body')).not.toContainText(/0 projects|0 results/i);
  });

  test('adds a project through the admin change form', async ({page}) => {
    await adminLogin(page);

    const projectTitle = `E2E Browser Added Project ${Date.now()}`;
    await expectAdminDocument(page, '/admin/projects/project/add/');

    await page.locator('select[name="semester"]').selectOption({label: '2099-2 Fall'});
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

  test('publishes semesters through the custom admin toolbar action', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/projects/semester/');

    await page.locator('#publish-all-confirmation').fill('publish all');
    await page.getByRole('button', {name: /publish all/i}).click();

    await expect(page).toHaveURL(/\/admin\/projects\/semester\//);
    await expect(page.locator('body')).toContainText(/semester\(s\) published/i);
  });
});
