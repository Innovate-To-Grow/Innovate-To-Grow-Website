import {expect, test} from '@playwright/test';

import {
  seededProjectTitle,
  seededSemesterLabel,
  adminLogin,
  expectAdminDocument,
  confirmAdminSaveIfRequired,
} from './adminFixtures';

// The live Django-admin suite, projects and semesters. Split by admin area into admin*.spec.ts; each file runs
// its flows serially. @admin pins this live, DB-mutating admin suite to the chromium project
// (see playwright.config.ts) — firefox/webkit and the mobile devices skip it.
test.describe.serial('Django admin browser flows', {tag: '@admin'}, () => {
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
    await confirmAdminSaveIfRequired(page, 'Project');

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
    await confirmAdminSaveIfRequired(page, 'Project');

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
});
