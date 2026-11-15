import {expect, test} from '@playwright/test';

import {
  seededEventTemplateName,
  adminLogin,
  expectAdminDocument,
} from './adminFixtures';

// The live Django-admin suite, events. Split by admin area into admin*.spec.ts; each file runs
// its flows serially. @admin pins this live, DB-mutating admin suite to the chromium project
// (see playwright.config.ts) — firefox/webkit and the mobile devices skip it.
test.describe.serial('Django admin browser flows', {tag: '@admin'}, () => {
  test('loads a safe Event template and enforces dependent contact options', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/event/event/add/');

    const sourceSelect = page.locator('#event-copy-source');
    await expect(sourceSelect).toBeVisible();
    await expect(page.locator('#id_collect_phone')).not.toBeChecked();
    await expect(page.locator('#id_verify_phone')).not.toBeChecked();
    await expect(page.locator('#id_verify_phone')).toBeDisabled();
    await expect(page.locator('#id_verify_phone')).toHaveAttribute(
      'aria-describedby',
      /event-phone-dependency-hint/,
    );
    await expect(page.locator('#event-phone-dependency-hint')).toContainText(
      'Enable Collect for Phone Number',
    );
    for (const field of ['require_phone', 'verify_secondary_email', 'require_secondary_email']) {
      await expect(page.locator(`#id_${field}`)).not.toBeChecked();
      await expect(page.locator(`#id_${field}`)).toBeDisabled();
    }
    await expect(page.locator('#id_verify_secondary_email')).toHaveAttribute(
      'aria-describedby', /event-secondary-email-dependency-hint/,
    );
    const sourceValue = await sourceSelect.locator('option', {hasText: seededEventTemplateName}).getAttribute('value');
    expect(sourceValue).not.toBeNull();

    const nameInput = page.locator('input[name="name"]');
    const startDate = page.locator('input[name="date"]');
    const endDate = page.locator('input[name="end_date"]');
    await nameInput.fill('Unsaved Event Name');
    await startDate.fill('2099-06-01');
    await expect(endDate).toHaveValue('2099-06-01');
    await startDate.fill('2099-06-03');
    await expect(endDate).toHaveValue('2099-06-03');
    await endDate.fill('2099-06-08');
    await startDate.fill('2099-06-04');
    await expect(endDate).toHaveValue('2099-06-08');

    await sourceSelect.selectOption(sourceValue!);
    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toContain('discard your unsaved Event, Ticket, and Question changes');
      await dialog.dismiss();
    });
    await page.getByRole('button', {name: /load event data/i}).click();
    await expect(page).not.toHaveURL(/\?copy_from=/);
    await expect(nameInput).toHaveValue('Unsaved Event Name');
    await expect(startDate).toHaveValue('2099-06-04');
    await expect(endDate).toHaveValue('2099-06-08');

    await page.reload({waitUntil: 'domcontentloaded'});
    await page.locator('#event-copy-source').selectOption(sourceValue!);
    await page.getByRole('button', {name: /load event data/i}).click();

    await expect(page).toHaveURL(/\/admin\/event\/event\/add\/\?copy_from=/);
    await expect(page.locator('body')).toContainText(`Loaded safe template data from ${seededEventTemplateName}`);
    await expect(page.getByRole('link', {name: '2 Ticket types'})).toHaveAttribute('href', '#tickets-group');
    await expect(page.getByRole('link', {name: '2 Questions'})).toHaveAttribute('href', '#questions-group');
    await expect(page.locator('input[name="name"]')).toHaveValue('');
    await expect(page.locator('input[name="slug"]')).toHaveValue('');
    await expect(page.locator('input[name="date"]')).toHaveValue('2099-05-14');
    await expect(page.locator('input[name="end_date"]')).toHaveValue('2099-05-16');
    await expect(page.locator('input[name="location"]')).toHaveValue('E2E Event Hall');
    await expect(page.locator('input[name="registration_open"]')).not.toBeChecked();
    await expect(page.locator('input[name="tickets-0-name"]')).toHaveValue('E2E General Admission');
    await expect(page.locator('input[name="questions-0-text"]')).toHaveValue('What brings you to the E2E Event?');

    await page.locator('input[name="date"]').fill('2099-06-01');
    await expect(page.locator('input[name="end_date"]')).toHaveValue('2099-06-03');
    await page.locator('input[name="end_date"]').fill('2099-06-10');
    await page.locator('input[name="date"]').fill('2099-06-02');
    await expect(page.locator('input[name="end_date"]')).toHaveValue('2099-06-10');

    const promptPhone = page.locator('#id_collect_phone');
    const verifyPhone = page.locator('#id_verify_phone');
    await expect(promptPhone).toBeChecked();
    await expect(verifyPhone).toBeChecked();
    await expect(verifyPhone).toBeEnabled();
    await expect(page.locator('#event-phone-dependency-hint')).toContainText(
      'Verify if provided and Required are available',
    );

    await promptPhone.uncheck();
    await expect(verifyPhone).not.toBeChecked();
    await expect(verifyPhone).toBeDisabled();

    await promptPhone.check();
    await expect(verifyPhone).toBeEnabled();
    await expect(verifyPhone).not.toBeChecked();
    for (const [collectField, verifyField, requiredField] of [
      ['collect_phone', 'verify_phone', 'require_phone'],
      ['allow_secondary_email', 'verify_secondary_email', 'require_secondary_email'],
    ]) {
      const collect = page.locator(`#id_${collectField}`);
      const verify = page.locator(`#id_${verifyField}`);
      const required = page.locator(`#id_${requiredField}`);
      await collect.check();
      await verify.check();
      await required.check();
      await collect.uncheck();
      await expect(verify).not.toBeChecked();
      await expect(required).not.toBeChecked();
      await expect(verify).toBeDisabled();
      await expect(required).toBeDisabled();
      await collect.check();
      await expect(verify).toBeEnabled();
      await expect(required).toBeEnabled();
      await expect(verify).not.toBeChecked();
      await expect(required).not.toBeChecked();
    }

  });

  test('copies Event Ticket types and Questions through confirmation', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/event/event/add/');

    const sourceSelect = page.locator('#event-copy-source');
    const sourceValue = await sourceSelect.locator('option', {hasText: seededEventTemplateName}).getAttribute('value');
    expect(sourceValue).not.toBeNull();
    await sourceSelect.selectOption(sourceValue!);
    await page.getByRole('button', {name: /load event data/i}).click();

    const copiedTicketName = 'E2E General Admission — copied and edited';
    const copiedQuestionText = 'What should we know about your E2E goals?';
    await expect(page.locator('input[name="tickets-0-name"]')).toBeVisible();
    await expect(page.locator('input[name="tickets-1-name"]')).toHaveValue('E2E VIP Admission');
    await expect(page.locator('input[name="questions-0-text"]')).toBeVisible();
    await expect(page.locator('input[name="questions-1-text"]')).toHaveValue(
      'Do you need accessibility accommodations?',
    );
    await page.locator('input[name="tickets-0-name"]').fill(copiedTicketName);
    await page.locator('input[name="questions-0-text"]').fill(copiedQuestionText);

    const suffix = Date.now().toString();
    const eventName = `E2E Copied Event ${suffix}`;
    const eventSlug = `e2e-copied-event-${suffix}`;
    await page.locator('input[name="name"]').fill(eventName);
    await page.locator('input[name="slug"]').fill(eventSlug);
    for (const field of [
      'collect_phone', 'verify_phone', 'require_phone',
      'allow_secondary_email', 'verify_secondary_email', 'require_secondary_email',
    ]) await page.locator(`#id_${field}`).check();
    await page.locator('button[name="_save"]').click();

    await expect(page).toHaveURL(/\/admin\/event\/event\/confirm-change\//);
    await expect(page.locator('body')).toContainText(copiedTicketName);
    await expect(page.locator('body')).toContainText('E2E VIP Admission');
    await expect(page.locator('body')).toContainText(copiedQuestionText);
    await expect(page.locator('body')).toContainText('Do you need accessibility accommodations?');
    await page.locator('#confirm-input').fill('Event');
    await page.locator('#confirm-btn').click();

    await expect(page).toHaveURL(/\/admin\/event\/event\//);
    await expect(page.locator('body')).toContainText(/was added successfully|added successfully/i);
    await page.locator('input[name="q"]').fill(eventName);
    await page.locator('input[name="q"]').press('Enter');
    await page.getByRole('link', {name: eventName}).first().click();
    await page.reload({waitUntil: 'domcontentloaded'});
    for (const field of [
      'collect_phone', 'verify_phone', 'require_phone',
      'allow_secondary_email', 'verify_secondary_email', 'require_secondary_email',
    ]) await expect(page.locator(`#id_${field}`)).toBeChecked();
    await expect(page.locator('input[name="tickets-0-name"]')).toHaveValue(copiedTicketName);
    await expect(page.locator('input[name="tickets-1-name"]')).toHaveValue('E2E VIP Admission');
    await expect(page.locator('input[name="questions-0-text"]')).toHaveValue(copiedQuestionText);
    await expect(page.locator('input[name="questions-1-text"]')).toHaveValue(
      'Do you need accessibility accommodations?',
    );
  });
});
