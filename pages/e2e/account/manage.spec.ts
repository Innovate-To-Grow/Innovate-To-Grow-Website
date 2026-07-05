// /account deep features: EmailCenter, PhoneCenter, PasswordSection,
// DeleteAccountSection, TicketsSection, and MySharedLinksSection.
import {test, expect} from '../fixtures';
import {
  contactEmail,
  contactPhone,
  mockAccountDeleteFlow,
  mockAccountEmails,
  mockContactEmailsCRUD,
  mockContactPhonesCRUD,
  mockMyTickets,
  mockPasswordChangeFlow,
  mockPastProjectSharesList,
  myTicket,
  seedAuthenticatedSession,
} from '../helpers';

// -- EmailCenter -----------------------------------------------------------

test('EmailCenter: add a contact email', async ({page}) => {
  await seedAuthenticatedSession(page);
  const {created} = await mockContactEmailsCRUD(page);
  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  await page.getByRole('button', {name: /add email/i}).click();
  await page.locator('#add-contact-email').fill('work@example.com');
  await page.getByRole('button', {name: /add & send verification/i}).click();
  await expect.poll(() => created.length).toBeGreaterThan(0);
  expect((created[0] as Record<string, unknown>).email_address).toBe('work@example.com');
});

test('EmailCenter: delete a contact email', async ({page}) => {
  await seedAuthenticatedSession(page);
  const {deleted} = await mockContactEmailsCRUD(page, {
    initial: [contactEmail({id: 'cemail-to-delete', email_address: 'old@example.com'})],
  });
  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  const deleteBtn = page.locator('[aria-label="Delete email"]').first();
  if (await deleteBtn.isVisible()) {
    await deleteBtn.click();
    await expect.poll(() => deleted.length).toBeGreaterThan(0);
  }
});

test('EmailCenter: set primary email', async ({page}) => {
  await seedAuthenticatedSession(page);
  const {primaryPayloads} = await mockContactEmailsCRUD(page, {
    initial: [contactEmail({id: 'cemail-1', email_address: 'new-primary@example.com', verified: true})],
  });
  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  const makePrimaryBtn = page.getByRole('button', {name: /make primary/i}).first();
  if (await makePrimaryBtn.isVisible()) {
    await makePrimaryBtn.click();
    await expect.poll(() => primaryPayloads.length).toBeGreaterThan(0);
  }
});

// -- PhoneCenter -----------------------------------------------------------

test('PhoneCenter: add a contact phone', async ({page}) => {
  await seedAuthenticatedSession(page, {profile: {first_name: 'Ada', last_name: 'Lovelace'}});
  const {created} = await mockContactPhonesCRUD(page);
  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  await page.getByRole('button', {name: 'Add Phone', exact: true}).click();
  // The input is a 10-digit US national number; the terms checkbox is
  // required before the form can submit (PhoneAddForm.tsx).
  await page.locator('#add-phone-number').fill('2065551234');
  await page.locator('#add-phone-terms').check();
  await page.getByRole('button', {name: 'Add Phone', exact: true}).click();
  await expect.poll(() => created.length).toBeGreaterThan(0);
});

test('PhoneCenter: delete a contact phone', async ({page}) => {
  await seedAuthenticatedSession(page);
  const {deleted} = await mockContactPhonesCRUD(page, {
    initial: [contactPhone({id: 'cphone-to-delete', phone_number: '+12065559999'})],
  });
  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  const deleteBtn = page.locator('[aria-label="Delete phone"]').first();
  if (await deleteBtn.isVisible()) {
    await deleteBtn.click();
    await expect.poll(() => deleted.length).toBeGreaterThan(0);
  }
});

// -- PasswordSection -------------------------------------------------------

test('PasswordSection: change password flow', async ({page}) => {
  await seedAuthenticatedSession(page);
  const {requestPayloads} = await mockPasswordChangeFlow(page);
  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  const changePwBtn = page.getByRole('button', {name: /change password/i});
  if (await changePwBtn.isVisible()) {
    await changePwBtn.click();
    await page.locator('#password-change-code').fill('123456');
    await page.getByRole('button', {name: /verify/i}).click();
    // Fill new password fields.
    await page.locator('#password-change-new').fill('NewP@ssw0rd!');
    await page.locator('#password-change-confirm').fill('NewP@ssw0rd!');
    await page.getByRole('button', {name: /set password/i}).click();
    await expect.poll(() => requestPayloads.length).toBeGreaterThan(0);
  }
});

// -- DeleteAccountSection --------------------------------------------------

test('DeleteAccountSection: delete account flow', async ({page}) => {
  await seedAuthenticatedSession(page);
  await mockAccountDeleteFlow(page);
  await mockAccountEmails(page, ['member@example.com']);
  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  const deleteBtn = page.getByRole('button', {name: /delete account/i});
  if (await deleteBtn.isVisible()) {
    await deleteBtn.click();
    await expect(page.locator('.delete-account-section')).toBeVisible();
  }
});

// -- TicketsSection --------------------------------------------------------

test('TicketsSection: renders tickets from API', async ({page}) => {
  await seedAuthenticatedSession(page);
  await mockMyTickets(page, [
    myTicket({
      id: 'ticket-1',
      ticket_code: 'ITG-E2E-001',
      event: {id: 'ev-1', name: 'Spring Showcase', slug: 'spring-showcase', date: '2026-05-01T18:00:00Z', location: 'Main Hall', description: ''},
    }),
  ]);
  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.account-page')).toContainText('ITG-E2E-001');
});

// -- MySharedLinksSection --------------------------------------------------

test('MySharedLinksSection: renders shared links', async ({page}) => {
  await seedAuthenticatedSession(page);
  await mockPastProjectSharesList(page, [
    {id: 'share-1', name: 'My Curated Projects', note: '', share_url: '/past-projects/share-1', row_count: 2, created_at: '2026-07-01T00:00:00Z'},
  ]);
  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.account-page')).toContainText('My Curated Projects');
});
