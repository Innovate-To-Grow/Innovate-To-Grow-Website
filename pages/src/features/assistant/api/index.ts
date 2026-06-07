import {isAxiosError} from 'axios';

import {api} from '@/lib/api-client';

/** A single turn in the chat transcript exchanged with the backend. */
export interface AssistantChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

/** Public configuration for the assistant widget (GET /assistant/config/). */
export interface AssistantConfig {
  enabled: boolean;
  welcome_message: string;
  starter_questions: string[];
  unavailable_message: string;
  max_message_chars: number;
}

/** Token accounting returned alongside a successful reply. */
export interface AssistantUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
}

/** Raw 200-success body for POST /assistant/chat/. */
export interface AssistantChatSuccessBody {
  available: true;
  reply: string;
  usage: AssistantUsage;
}

/** Raw 200-unavailable body for POST /assistant/chat/. */
export interface AssistantChatUnavailableBody {
  available: false;
  message: string;
}

type AssistantChatBody = AssistantChatSuccessBody | AssistantChatUnavailableBody;

/**
 * Normalized result of a chat call. The component switches on `status` and
 * never has to touch axios internals or HTTP status codes directly.
 */
export type AssistantChatResult =
  | {status: 'ok'; reply: string; usage: AssistantUsage}
  | {status: 'unavailable'; message: string}
  | {status: 'budget'; message: string}
  | {status: 'error'; message: string};

/** Sent to the server when classification falls through to a generic failure. */
const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.';

/** Shown when the request is rejected for hitting the usage budget (HTTP 429). */
const BUDGET_ERROR_MESSAGE = "You've reached the message limit for now, please try again later.";

/** Hardcoded defaults so the widget still renders if the config fetch fails. */
export const DEFAULT_ASSISTANT_CONFIG: AssistantConfig = {
  enabled: true,
  welcome_message: 'Hi! I can help answer questions about Innovate to Grow. What would you like to know?',
  starter_questions: [
    'What is Innovate to Grow?',
    'How do I get involved as a sponsor?',
    'When is the next event?',
  ],
  unavailable_message: 'The assistant is currently unavailable. Please check back later.',
  max_message_chars: 2000,
};

/**
 * Fetch the public assistant configuration. Throws on network/HTTP errors so
 * the caller can decide whether to fall back to {@link DEFAULT_ASSISTANT_CONFIG}.
 */
export async function fetchAssistantConfig(): Promise<AssistantConfig> {
  const response = await api.get<AssistantConfig>('/assistant/config/');
  return response.data;
}

/** True when an error represents an HTTP 429 budget-exceeded response. */
export function isBudgetError(error: unknown): boolean {
  return isAxiosError(error) && error.response?.status === 429;
}

/**
 * Send a chat message and classify the outcome into a discriminated union.
 *
 * The function never throws: every transport/HTTP failure is mapped to an
 * `error` (or `budget`) result so the component's render logic stays simple.
 *
 * `sessionId` is an opaque per-conversation id sent as `session_id` so the
 * backend can correlate turns within a single conversation.
 */
export async function sendAssistantMessage(
  message: string,
  history: AssistantChatMessage[],
  sessionId: string,
): Promise<AssistantChatResult> {
  try {
    const response = await api.post<AssistantChatBody>('/assistant/chat/', {
      message,
      history,
      session_id: sessionId,
    });
    const body = response.data;
    if (body.available) {
      return {status: 'ok', reply: body.reply, usage: body.usage};
    }
    return {status: 'unavailable', message: body.message};
  } catch (error) {
    if (isBudgetError(error)) {
      return {status: 'budget', message: BUDGET_ERROR_MESSAGE};
    }
    return {status: 'error', message: GENERIC_ERROR_MESSAGE};
  }
}
