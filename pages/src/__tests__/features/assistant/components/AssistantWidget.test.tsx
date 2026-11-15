import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {AssistantChatResult, AssistantConfig} from '@/features/assistant/api';

const hoisted = vi.hoisted(() => {
  const DEFAULT_CONFIG = {
    enabled: true,
    welcome_message: 'Welcome! Ask me anything.',
    starter_questions: ['What is I2G?'],
    unavailable_message: 'Assistant is offline.',
    max_message_chars: 2000,
  };
  return {
    DEFAULT_CONFIG,
    fetchAssistantConfig: vi.fn(),
    sendAssistantMessage: vi.fn(),
  };
});

const mocks = hoisted;
const DEFAULT_CONFIG: AssistantConfig = hoisted.DEFAULT_CONFIG;

vi.mock('@/features/assistant/api', () => ({
  DEFAULT_ASSISTANT_CONFIG: hoisted.DEFAULT_CONFIG,
  fetchAssistantConfig: () => hoisted.fetchAssistantConfig(),
  sendAssistantMessage: (message: string, history: unknown, sessionId: string) =>
    hoisted.sendAssistantMessage(message, history, sessionId),
}));

import {AssistantWidget} from '@/features/assistant/components/AssistantWidget';

const okResult = (reply: string): AssistantChatResult => ({
  status: 'ok',
  reply,
  usage: {inputTokens: 1, outputTokens: 1, totalTokens: 2},
});

async function renderAndOpen() {
  render(<AssistantWidget />);
  fireEvent.click(screen.getByRole('button', {name: /open chat assistant/i}));
  await waitFor(() => expect(mocks.fetchAssistantConfig).toHaveBeenCalled());
}

function typeMessage(text: string) {
  fireEvent.change(screen.getByLabelText('Message'), {target: {value: text}});
}

function clickSend() {
  fireEvent.click(screen.getByRole('button', {name: 'Send'}));
}

/** Fixed session id so assertions don't depend on a random UUID. */
const SESSION_ID = 'test-session-id';

describe('AssistantWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    // Deterministic session id; jsdom may also lack crypto.randomUUID.
    vi.stubGlobal('crypto', {randomUUID: () => SESSION_ID});
    mocks.fetchAssistantConfig.mockResolvedValue(DEFAULT_CONFIG);
    mocks.sendAssistantMessage.mockResolvedValue(okResult('Hello from the assistant'));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it('renders the launcher button', () => {
    render(<AssistantWidget />);
    expect(screen.getByRole('button', {name: /open chat assistant/i})).toBeInTheDocument();
  });

  it('opens the panel on launcher click and closes it', async () => {
    await renderAndOpen();
    expect(screen.getByRole('dialog', {name: /chat assistant/i})).toBeInTheDocument();
    expect(screen.getByText('Welcome! Ask me anything.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: /close chat assistant/i}));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('submits a typed message and renders the returned reply', async () => {
    await renderAndOpen();

    typeMessage('How do sponsors join?');
    clickSend();

    await waitFor(() => expect(mocks.sendAssistantMessage).toHaveBeenCalled());
    // The new message goes in `message`; history holds ONLY prior turns (empty here).
    expect(mocks.sendAssistantMessage).toHaveBeenCalledWith('How do sponsors join?', [], SESSION_ID);
    expect(await screen.findByText('Hello from the assistant')).toBeInTheDocument();
    expect(screen.getByText('How do sponsors join?')).toBeInTheDocument();
  });

  it('submits a starter question chip', async () => {
    await renderAndOpen();
    fireEvent.click(screen.getByRole('button', {name: 'What is I2G?'}));

    await waitFor(() =>
      expect(mocks.sendAssistantMessage).toHaveBeenCalledWith('What is I2G?', expect.anything(), SESSION_ID),
    );
    expect(await screen.findByText('Hello from the assistant')).toBeInTheDocument();
  });

  it('sends prior turns (not the current message) as history on a second message', async () => {
    mocks.sendAssistantMessage.mockResolvedValueOnce(okResult('first reply'));
    await renderAndOpen();

    typeMessage('first question');
    clickSend();
    expect(await screen.findByText('first reply')).toBeInTheDocument();

    mocks.sendAssistantMessage.mockResolvedValueOnce(okResult('second reply'));
    typeMessage('second question');
    clickSend();
    expect(await screen.findByText('second reply')).toBeInTheDocument();

    // Second call: message = 'second question'; history = the two prior turns,
    // and crucially does NOT include 'second question'.
    expect(mocks.sendAssistantMessage).toHaveBeenLastCalledWith(
      'second question',
      [
        {role: 'user', content: 'first question'},
        {role: 'assistant', content: 'first reply'},
      ],
      SESSION_ID,
    );
  });
});
