import {isAxiosError} from 'axios';

import {adoptVisitorToken, getVisitorToken, storeVisitorToken} from '@/features/assistant/utils/visitorToken';
import {api} from '@/lib/api';

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
  /**
   * Server-signed visitor identity for this browser. Optional: older backends
   * do not send it, and it is omitted while the assistant is disabled.
   */
  visitor_token?: string;
}

/** Token accounting returned alongside a successful reply. */
export interface AssistantUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
}

/**
 * Present on a chat response (success or error) only when the backend wants
 * this browser to replace its visitor token: the one sent was missing, expired
 * or not accepted, or is due for renewal.
 */
interface AssistantVisitorHandover {
  visitor_token?: string;
}

/** Raw 200-success body for POST /assistant/chat/. */
export interface AssistantChatSuccessBody extends AssistantVisitorHandover {
  available: true;
  reply: string;
  usage: AssistantUsage;
}

/** Raw 200-unavailable body for POST /assistant/chat/. */
export interface AssistantChatUnavailableBody extends AssistantVisitorHandover {
  available: false;
  message: string;
}

/** Request body for POST /assistant/chat/. */
interface AssistantChatRequest {
  message: string;
  history: AssistantChatMessage[];
  session_id: string;
  /** Sent in the body (not a header) so no CORS allow-list change is needed. */
  visitor_token?: string;
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

/**
 * Shown when the request is rejected for hitting a usage limit (HTTP 429).
 * Deliberately impersonal: the limit may be one shared by every visitor (the
 * site-wide budget), so it must not blame the person who just asked.
 */
const BUDGET_ERROR_MESSAGE = 'The assistant has reached its usage limit for now. Please try again later.';

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
 *
 * Side effect: if this browser holds no visitor token yet, the one offered by
 * the config response is stored for later chat calls.
 */
export async function fetchAssistantConfig(): Promise<AssistantConfig> {
  const response = await api.get<AssistantConfig>('/assistant/config/');
  adoptVisitorToken(response.data?.visitor_token);
  return response.data;
}

/** True when an error represents an HTTP 429 budget-exceeded response. */
export function isBudgetError(error: unknown): boolean {
  return isAxiosError(error) && error.response?.status === 429;
}

/** Store the replacement visitor token carried by a chat response body, if any. */
function storeVisitorHandover(body: unknown): void {
  if (!body || typeof body !== 'object') return;
  storeVisitorToken((body as Record<string, unknown>).visitor_token);
}

/** Return only the public-safe message fields emitted by the assistant API. */
function assistantApiErrorMessage(error: unknown): string | null {
  if (!isAxiosError(error)) return null;
  const data: unknown = error.response?.data;
  if (!data || typeof data !== 'object') return null;
  const body = data as Record<string, unknown>;
  for (const key of ['detail', 'message']) {
    const value = body[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
}

/** One POST /assistant/chat/, classified. Never throws. */
async function postChat(
  message: string,
  history: AssistantChatMessage[],
  sessionId: string,
): Promise<{result: AssistantChatResult; identityReplaced: boolean}> {
  const request: AssistantChatRequest = {message, history, session_id: sessionId};
  const sentToken = getVisitorToken();
  if (sentToken !== null) request.visitor_token = sentToken;
  let result: AssistantChatResult;
  try {
    const response = await api.post<AssistantChatBody>('/assistant/chat/', request);
    const body = response.data;
    storeVisitorHandover(body);
    result = body.available
      ? {status: 'ok', reply: body.reply, usage: body.usage}
      : {status: 'unavailable', message: body.message};
  } catch (error) {
    if (isAxiosError(error)) storeVisitorHandover(error.response?.data);
    result = isBudgetError(error)
      ? {status: 'budget', message: BUDGET_ERROR_MESSAGE}
      : {status: 'error', message: assistantApiErrorMessage(error) ?? GENERIC_ERROR_MESSAGE};
  }
  return {result, identityReplaced: getVisitorToken() !== sentToken};
}

/**
 * Send a chat message and classify the outcome into a discriminated union.
 *
 * The function never throws: every transport/HTTP failure is mapped to an
 * `error` (or `budget`) result so the component's render logic stays simple.
 *
 * `sessionId` is an opaque per-conversation id sent as `session_id` so the
 * backend can correlate turns within a single conversation.
 *
 * The held visitor token (if any) is sent as `visitor_token`, and a
 * replacement handed back by the backend is stored for the next call.
 *
 * A 429 that hands back a replacement was judged without a valid token, i.e.
 * in the bucket shared by every such caller. The message is then re-sent ONCE
 * with the new token, so a lapsed token never costs the visitor an answer just
 * because that shared bucket happened to be full.
 */
export async function sendAssistantMessage(
  message: string,
  history: AssistantChatMessage[],
  sessionId: string,
): Promise<AssistantChatResult> {
  const first = await postChat(message, history, sessionId);
  if (first.result.status === 'budget' && first.identityReplaced) {
    return (await postChat(message, history, sessionId)).result;
  }
  return first.result;
}
