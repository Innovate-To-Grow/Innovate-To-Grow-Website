// /login password mode: email + encrypted-password login via /authn/login/.
import {test, expect} from '../fixtures';
import {
  mockAccountDashboard,
  mockPasswordLogin,
  mockPublicKey,
} from '../helpers';

test('switch from identifier mode to password mode', async ({page}) => {
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  // The identifier mode should render the "use password" link.
  await expect(page.getByText(/sign in with password/i)).toBeVisible();
  await page.getByText(/sign in with password/i).click();
  // Password form should now be visible.
  await expect(page.getByLabel(/password/i)).toBeVisible();
});

test('password form renders email and password fields', async ({page}) => {
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.getByText(/sign in with password/i).click();
  // Email/phone input and password input should both be present.
  await expect(page.locator('input[type="password"]')).toBeVisible();
});

test('successful password login redirects to /account', async ({page}) => {
  await mockPublicKey(page);
  const {loginPayloads} = await mockPasswordLogin(page);
  await mockAccountDashboard(page);

  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.getByText(/sign in with password/i).click();
  await page.locator('#login-email').fill('member@example.com');
  await page.locator('input[type="password"]').fill('correct-password');
  await page.locator('#root').getByRole('button', {name: 'Sign In', exact: true}).click();

  await expect.poll(() => loginPayloads.length).toBeGreaterThan(0);
  await expect(page).toHaveURL(/\/account/);
});

test('invalid credentials show error message', async ({page}) => {
  await mockPublicKey(page);
  await mockPasswordLogin(page, {status: 401});

  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.getByText(/sign in with password/i).click();
  await page.locator('#login-email').fill('wrong@example.com');
  await page.locator('input[type="password"]').fill('wrong');
  await page.locator('#root').getByRole('button', {name: 'Sign In', exact: true}).click();

  await expect(page.locator('.auth-alert.error')).toBeVisible();
});

test('switch back from password mode to identifier mode', async ({page}) => {
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.getByText(/sign in with password/i).click();
  await expect(page.locator('input[type="password"]')).toBeVisible();
  // The link to switch back should be present.
  await page.getByRole('button', {name: /sign in with a verification code/i}).click();
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
});
