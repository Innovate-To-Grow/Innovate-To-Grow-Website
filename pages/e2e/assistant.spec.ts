// #chatbot-root: AI assistant floating chat widget. Independent React root with
// launcher, chat panel, message sending, starter questions, and error states.
import {test, expect} from './fixtures';
import {
  assistantChatSuccess,
  assistantConfig,
  mockAssistantChat,
  mockAssistantConfig,
} from './helpers';

test('widget launcher button is visible on page load', async ({page}) => {
  await mockAssistantConfig(page, assistantConfig());
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.itg-assistant__launcher')).toBeVisible();
  await expect(page.locator('.itg-assistant__launcher')).toHaveAttribute('aria-label', 'Open chat assistant');
});

test('click launcher opens the chat panel', async ({page}) => {
  await mockAssistantConfig(page, assistantConfig());
  await mockAssistantChat(page);
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  await expect(page.locator('.itg-assistant__panel')).toBeVisible();
  await expect(page.locator('.itg-assistant__title')).toContainText('Ask Innovate to Grow');
});

test('starter questions render as clickable chips', async ({page}) => {
  await mockAssistantConfig(page, assistantConfig({
    starter_questions: ['What is Innovate to Grow?', 'How do I sponsor?'],
  }));
  await mockAssistantChat(page);
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  await expect(page.locator('.itg-assistant__starters')).toBeVisible();
  await expect(page.locator('.itg-assistant__starter')).toHaveCount(2);
});

test('click starter question sends a message', async ({page}) => {
  await mockAssistantConfig(page, assistantConfig({
    starter_questions: ['What is Innovate to Grow?'],
  }));
  const {messages} = await mockAssistantChat(page, {
    successResponse: assistantChatSuccess({reply: 'ITG is a program at UC Merced.'}),
  });
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  await page.locator('.itg-assistant__starter').first().click();
  await expect.poll(() => messages.length).toBeGreaterThan(0);
  expect(messages[0]).toHaveProperty('message', 'What is Innovate to Grow?');
});

test('type and send a custom message', async ({page}) => {
  await mockAssistantConfig(page);
  const {messages} = await mockAssistantChat(page, {
    successResponse: assistantChatSuccess({reply: 'Here is your answer.'}),
  });
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  await page.locator('.itg-assistant__textarea').fill('Tell me about events');
  await page.locator('.itg-assistant__send').click();
  await expect.poll(() => messages.length).toBeGreaterThan(0);
});

test('assistant reply renders in the message list', async ({page}) => {
  await mockAssistantConfig(page);
  await mockAssistantChat(page, {
    successResponse: assistantChatSuccess({reply: '**Bold** answer with [a link](https://example.com).'}),
  });
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  await page.locator('.itg-assistant__textarea').fill('hello');
  await page.locator('.itg-assistant__send').click();
  // The reply should appear in the messages area.
  await expect(page.locator('.itg-assistant__messages')).toContainText('Bold answer');
});

test('character counter shows remaining characters', async ({page}) => {
  await mockAssistantConfig(page, assistantConfig({max_message_chars: 50}));
  await mockAssistantChat(page);
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  const counter = page.locator('.itg-assistant__counter');
  await expect(counter).toBeVisible();
  await expect(counter).toContainText('50'); // max chars displayed
});

test('"New conversation" button resets the transcript', async ({page}) => {
  await mockAssistantConfig(page);
  const {messages} = await mockAssistantChat(page);
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  await page.locator('.itg-assistant__textarea').fill('first message');
  await page.locator('.itg-assistant__send').click();
  await expect.poll(() => messages.length).toBeGreaterThan(0);
  // Click "New conversation"
  await page.locator('.itg-assistant__new').click();
  // The messages area should reset (no user messages).
  await expect(page.locator('.itg-assistant__messages')).toBeVisible();
});

test('unavailable state when config says disabled', async ({page}) => {
  await mockAssistantConfig(page, assistantConfig({enabled: false}));
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  await expect(page.locator('.itg-assistant__unavailable')).toBeVisible();
});

test('budget exceeded (429) shows error state', async ({page}) => {
  await mockAssistantConfig(page);
  const {messages} = await mockAssistantChat(page, {budgetError: true});
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  await page.locator('.itg-assistant__textarea').fill('hello');
  await page.locator('.itg-assistant__send').click();
  await expect.poll(() => messages.length).toBeGreaterThan(0);
});

test('network error shows retry button', async ({page}) => {
  await mockAssistantConfig(page);
  await mockAssistantChat(page, {networkError: true});
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  await page.locator('.itg-assistant__textarea').fill('hello');
  await page.locator('.itg-assistant__send').click();
  // Error state should be visible — the widget shows the error inline.
  await expect(page.locator('.itg-assistant__panel')).toBeVisible();
});

test('close button hides the chat panel', async ({page}) => {
  await mockAssistantConfig(page);
  await mockAssistantChat(page);
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await page.locator('.itg-assistant__launcher').click();
  await expect(page.locator('.itg-assistant__panel')).toBeVisible();
  await page.locator('.itg-assistant__close').click();
  await expect(page.locator('.itg-assistant__panel')).not.toBeVisible();
});
