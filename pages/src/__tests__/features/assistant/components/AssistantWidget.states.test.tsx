import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
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

  it('shows a loading indicator while the reply is pending, then the reply', async () => {
    let resolve: (value: AssistantChatResult) => void = () => {};
    mocks.sendAssistantMessage.mockReturnValue(
      new Promise<AssistantChatResult>((r) => {
        resolve = r;
      }),
    );

    await renderAndOpen();
    typeMessage('ping');
    clickSend();

    expect(await screen.findByLabelText('Assistant is typing')).toBeInTheDocument();

    resolve(okResult('pong'));
    expect(await screen.findByText('pong')).toBeInTheDocument();
    expect(screen.queryByLabelText('Assistant is typing')).not.toBeInTheDocument();
  });

  it('shows an error state with retry when the call returns an error', async () => {
    mocks.sendAssistantMessage.mockResolvedValueOnce({status: 'error', message: 'Something went wrong.'});

    await renderAndOpen();
    typeMessage('boom');
    clickSend();

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Something went wrong.')).toBeInTheDocument();

    // Retry re-sends the last attempt and clears the error on success.
    mocks.sendAssistantMessage.mockResolvedValueOnce(okResult('recovered'));
    fireEvent.click(within(alert).getByRole('button', {name: /try again/i}));
    expect(await screen.findByText('recovered')).toBeInTheDocument();

    // Retry must NOT append a duplicate user bubble.
    expect(screen.getAllByText('boom')).toHaveLength(1);
    // Retry re-sends with the same message and prior history (empty here),
    // without re-adding the failed user turn.
    expect(mocks.sendAssistantMessage).toHaveBeenLastCalledWith('boom', [], SESSION_ID);
  });

  it('shows a budget-specific error on 429-classified results', async () => {
    mocks.sendAssistantMessage.mockResolvedValueOnce({
      status: 'budget',
      message: 'The assistant has reached its usage limit for now. Please try again later.',
    });

    await renderAndOpen();
    typeMessage('too much');
    clickSend();

    expect(await screen.findByText(/assistant has reached its usage limit/i)).toBeInTheDocument();
  });

  it('renders the unavailable message and disables input when config is disabled', async () => {
    mocks.fetchAssistantConfig.mockResolvedValue({...DEFAULT_CONFIG, enabled: false});

    render(<AssistantWidget />);
    fireEvent.click(screen.getByRole('button', {name: /open chat assistant/i}));
    await waitFor(() => expect(mocks.fetchAssistantConfig).toHaveBeenCalled());

    expect(screen.getByText('Assistant is offline.')).toBeInTheDocument();
    expect(screen.getByLabelText('Message')).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Send'})).toBeDisabled();
  });

  it('switches to the unavailable state when a chat call reports unavailable', async () => {
    mocks.sendAssistantMessage.mockResolvedValueOnce({status: 'unavailable', message: 'Temporarily down.'});

    await renderAndOpen();
    typeMessage('are you there');
    clickSend();

    expect(await screen.findByText('Temporarily down.')).toBeInTheDocument();
    expect(screen.getByLabelText('Message')).toBeDisabled();
  });

  it('does not submit on Enter while an IME composition is in progress', async () => {
    await renderAndOpen();
    const input = screen.getByLabelText('Message');
    fireEvent.change(input, {target: {value: '你好'}});
    // Enter that confirms an IME candidate reports isComposing=true.
    fireEvent.keyDown(input, {key: 'Enter', isComposing: true});
    expect(mocks.sendAssistantMessage).not.toHaveBeenCalled();
    // A normal Enter (composition finished) submits.
    fireEvent.keyDown(input, {key: 'Enter'});
    await waitFor(() => expect(mocks.sendAssistantMessage).toHaveBeenCalledWith('你好', [], SESSION_ID));
  });

  it('treats max_message_chars <= 0 as unlimited (no counter, long message sendable)', async () => {
    mocks.fetchAssistantConfig.mockResolvedValue({...DEFAULT_CONFIG, max_message_chars: 0});
    await renderAndOpen();

    typeMessage('x'.repeat(5000));
    // No counter is rendered when there is no limit.
    expect(screen.queryByText(/\/0$/)).not.toBeInTheDocument();
    clickSend();
    await waitFor(() => expect(mocks.sendAssistantMessage).toHaveBeenCalledWith('x'.repeat(5000), [], SESSION_ID));
  });

  it('falls back to default config when the config fetch fails', async () => {
    mocks.fetchAssistantConfig.mockRejectedValue(new Error('network'));

    render(<AssistantWidget />);
    fireEvent.click(screen.getByRole('button', {name: /open chat assistant/i}));
    await waitFor(() => expect(mocks.fetchAssistantConfig).toHaveBeenCalled());

    // The default config (DEFAULT_ASSISTANT_CONFIG) welcome message still renders.
    expect(screen.getByText('Welcome! Ask me anything.')).toBeInTheDocument();
    expect(screen.getByLabelText('Message')).not.toBeDisabled();
  });
});
