import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
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

  it('restores a persisted transcript on mount and hides the starters', async () => {
    sessionStorage.setItem(
      'itg-assistant-transcript',
      JSON.stringify([
        {id: 'r1', role: 'user', content: 'restored question'},
        {id: 'r2', role: 'assistant', content: 'restored reply'},
      ]),
    );

    await renderAndOpen();

    expect(await screen.findByText('restored question')).toBeInTheDocument();
    expect(await screen.findByText('restored reply')).toBeInTheDocument();
    // A non-empty restored transcript means no starter chips are shown.
    expect(screen.queryByRole('button', {name: 'What is I2G?'})).not.toBeInTheDocument();
  });

  it('mints non-colliding message ids after a transcript restore', async () => {
    // Realistic createId() output: the module counter resets on reload, so
    // without re-seeding the next minted id would collide with restored "m1".
    sessionStorage.setItem(
      'itg-assistant-transcript',
      JSON.stringify([
        {id: 'm1', role: 'user', content: 'restored question'},
        {id: 'm2', role: 'assistant', content: 'restored reply'},
      ]),
    );

    await renderAndOpen();
    typeMessage('fresh question');
    clickSend();
    expect(await screen.findByText('Hello from the assistant')).toBeInTheDocument();

    const ids = Array.from(document.querySelectorAll('[data-message-id]')).map((node) =>
      node.getAttribute('data-message-id'),
    );
    expect(ids).toHaveLength(4);
    expect(new Set(ids).size).toBe(4);
  });

  it('drops an in-flight reply when New conversation is clicked mid-request', async () => {
    let resolve: (value: AssistantChatResult) => void = () => {};
    mocks.sendAssistantMessage.mockReturnValue(
      new Promise<AssistantChatResult>((r) => {
        resolve = r;
      }),
    );

    await renderAndOpen();
    typeMessage('old question');
    clickSend();
    expect(await screen.findByLabelText('Assistant is typing')).toBeInTheDocument();

    // Reset while the request is still pending, then let it resolve late.
    fireEvent.click(screen.getByRole('button', {name: /start a new conversation/i}));
    resolve(okResult('ghost reply'));
    // Flush the stale promise chain so a buggy dispatch would have rendered.
    await act(async () => {
      await Promise.resolve();
    });

    // The stale reply must not leak into the fresh conversation.
    expect(screen.queryByText('ghost reply')).not.toBeInTheDocument();
    expect(screen.queryByText('old question')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'What is I2G?'})).toBeInTheDocument();
  });

  it('passes the persisted session id to sendAssistantMessage', async () => {
    sessionStorage.setItem('itg-assistant-session', 'persisted-session');

    await renderAndOpen();
    typeMessage('hi');
    clickSend();

    await waitFor(() => expect(mocks.sendAssistantMessage).toHaveBeenCalledWith('hi', [], 'persisted-session'));
  });

  it('clears the transcript and shows starters again on New conversation', async () => {
    await renderAndOpen();

    typeMessage('a question');
    clickSend();
    expect(await screen.findByText('Hello from the assistant')).toBeInTheDocument();
    // Starters are gone once the conversation has turns.
    expect(screen.queryByRole('button', {name: 'What is I2G?'})).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: /start a new conversation/i}));

    // Transcript is emptied and the starter chip returns.
    expect(screen.queryByText('a question')).not.toBeInTheDocument();
    expect(screen.queryByText('Hello from the assistant')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'What is I2G?'})).toBeInTheDocument();
    // The persisted transcript is cleared too.
    expect(sessionStorage.getItem('itg-assistant-transcript')).toBe('[]');
  });
});
