import type {Page} from '@playwright/test';
import type {
  ContactEmail,
  ContactPhone,
} from '../../src/features/auth/api/contracts/types';
import {mockSendVerification} from './authFlows';
import {json} from './json';

// -- contact emails CRUD -----------------------------------------------------

export interface ContactEmailsMockResult {
  created: unknown[];
  updated: unknown[];
  deleted: string[];
  primaryPayloads: unknown[];
}

export async function mockContactEmailsCRUD(
  page: Page,
  opts: {initial?: ContactEmail[]} = {},
): Promise<ContactEmailsMockResult> {
  const emails: ContactEmail[] = opts.initial ?? [];
  const created: unknown[] = [];
  const updated: unknown[] = [];
  const deleted: string[] = [];
  const primaryPayloads: unknown[] = [];

  await mockSendVerification(page);

  // GET list
  await page.route('**/authn/contact-emails/', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill(json(emails));
      return;
    }
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      created.push(body);
      const newEmail: ContactEmail = {
        id: `cemail-${Date.now()}`,
        email_address: (body.email_address as string) ?? 'new@example.com',
        email_type: (body.email_type as ContactEmail['email_type']) ?? 'secondary',
        subscribe: (body.subscribe as boolean) ?? false,
        verified: false,
        created_at: new Date().toISOString(),
      };
      emails.push(newEmail);
      await route.fulfill(json(newEmail, 201));
      return;
    }
    await route.fulfill(json({detail: 'Method not allowed.'}, 405));
  });

  // Detail routes: PATCH, DELETE, make-primary, request-verification, verify-code
  await page.route(/\/authn\/contact-emails\/[^/]+\/.*$/, async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.replace(/\/$/, '').split('/');
    const id = parts[parts.length - 2]; // contact-emails/{id}/make-primary/
    const action = parts[parts.length - 1];

    if (action === 'make-primary') {
      primaryPayloads.push({id});
      await route.fulfill(json({message: 'Primary email updated.'}));
      return;
    }
    if (action === 'request-verification') {
      await route.fulfill(
        json({
          message: 'Verification code sent.',
          challenge_id: '87f80894-955d-49d7-b5f3-2aed231087b1',
        }),
      );
      return;
    }
    if (action === 'verify-code') {
      await route.fulfill(json({message: 'Email verified.'}));
      return;
    }
    await route.fulfill(json({detail: 'Not found.'}, 404));
  });

  await page.route(/\/authn\/contact-emails\/[^/]+\/?$/, async (route) => {
    const url = new URL(route.request().url());
    const id = url.pathname.replace(/\/$/, '').split('/').pop() ?? '';
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      updated.push({id, ...body});
      await route.fulfill(json({message: 'Updated.'}));
      return;
    }
    if (route.request().method() === 'DELETE') {
      deleted.push(id);
      await route.fulfill({status: 204});
      return;
    }
    await route.fulfill(json({detail: 'Not found.'}, 404));
  });

  return {created, updated, deleted, primaryPayloads};
}

// -- contact phones CRUD -----------------------------------------------------

export interface ContactPhonesMockResult {
  created: unknown[];
  updated: unknown[];
  deleted: string[];
}

export async function mockContactPhonesCRUD(
  page: Page,
  opts: {initial?: ContactPhone[]} = {},
): Promise<ContactPhonesMockResult> {
  const phones: ContactPhone[] = opts.initial ?? [];
  const created: unknown[] = [];
  const updated: unknown[] = [];
  const deleted: string[] = [];

  await mockSendVerification(page);

  await page.route('**/authn/contact-phones/', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill(json(phones));
      return;
    }
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      created.push(body);
      const newPhone: ContactPhone = {
        id: `cphone-${Date.now()}`,
        phone_number: (body.phone_number as string) ?? '+12065551234',
        region: (body.region as string) ?? '1-US',
        region_display: 'United States',
        subscribe: (body.subscribe as boolean) ?? false,
        verified: false,
        created_at: new Date().toISOString(),
      };
      phones.push(newPhone);
      await route.fulfill(json(newPhone, 201));
      return;
    }
    await route.fulfill(json({detail: 'Method not allowed.'}, 405));
  });

  // Detail routes: PATCH, DELETE, request-verification, verify-code
  await page.route(/\/authn\/contact-phones\/[^/]+\/.*$/, async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.replace(/\/$/, '').split('/');
    const action = parts[parts.length - 1];

    if (action === 'request-verification') {
      await route.fulfill(json({message: 'Verification code sent.'}));
      return;
    }
    if (action === 'verify-code') {
      await route.fulfill(json({message: 'Phone verified.'}));
      return;
    }
    await route.fulfill(json({detail: 'Not found.'}, 404));
  });

  await page.route(/\/authn\/contact-phones\/[^/]+\/?$/, async (route) => {
    const url = new URL(route.request().url());
    const id = url.pathname.replace(/\/$/, '').split('/').pop() ?? '';
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      updated.push({id, ...body});
      await route.fulfill(json({message: 'Updated.'}));
      return;
    }
    if (route.request().method() === 'DELETE') {
      deleted.push(id);
      await route.fulfill({status: 204});
      return;
    }
    await route.fulfill(json({detail: 'Not found.'}, 404));
  });

  return {created, updated, deleted};
}
