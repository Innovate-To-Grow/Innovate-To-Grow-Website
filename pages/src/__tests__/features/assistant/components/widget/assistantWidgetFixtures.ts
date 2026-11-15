import {fireEvent, screen} from '@testing-library/react';

import type {AssistantChatResult} from '@/features/assistant/api';

export const okResult = (reply: string): AssistantChatResult => ({
  status: 'ok',
  reply,
  usage: {inputTokens: 1, outputTokens: 1, totalTokens: 2},
});

export function typeMessage(text: string) {
  fireEvent.change(screen.getByLabelText('Message'), {target: {value: text}});
}

export function clickSend() {
  fireEvent.click(screen.getByRole('button', {name: 'Send'}));
}

/** Fixed session id so assertions don't depend on a random UUID. */
export const SESSION_ID = 'test-session-id';
