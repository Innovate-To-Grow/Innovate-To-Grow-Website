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

import {AssistantWidget} from '@/features/assistant/components/widget/AssistantWidget';
import {clickSend, okResult, SESSION_ID, typeMessage} from '@/__tests__/features/assistant/components/widget/assistantWidgetFixtures';

async function renderAndOpen() {
  render(<AssistantWidget />);
  fireEvent.click(screen.getByRole('button', {name: /open chat assistant/i}));
  await waitFor(() => expect(mocks.fetchAssistantConfig).toHaveBeenCalled());
}

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
});
