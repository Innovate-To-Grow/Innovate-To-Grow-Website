import type {AssistantChatMessage} from '@/features/assistant/api';

import {loadTranscript} from '../utils/sessionStore';
import type {DisplayMessage} from './types';

/** Max conversation turns sent to the backend (keeps payloads bounded). */
const MAX_HISTORY_TURNS = 10;

export interface ChatState {
  messages: DisplayMessage[];
  loading: boolean;
  error: string | null;
  /** When true, the backend reported the assistant is unavailable. */
  unavailable: string | null;
}

type ChatAction =
  | {type: 'send'; message: DisplayMessage}
  | {type: 'reply'; message: DisplayMessage}
  | {type: 'error'; message: string}
  | {type: 'unavailable'; message: string}
  | {type: 'retry'}
  | {type: 'reset'};

export const initialState: ChatState = {messages: [], loading: false, error: null, unavailable: null};

/** Lazy-init reducer state from any transcript persisted in sessionStorage. */
export function initState(): ChatState {
  const messages = loadTranscript();
  seedIdCounter(messages);
  return {...initialState, messages};
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'send':
      return {...state, messages: [...state.messages, action.message], loading: true, error: null};
    case 'reply':
      return {...state, loading: false, messages: [...state.messages, action.message]};
    case 'error':
      // error and unavailable are mutually exclusive; clear the other.
      return {...state, loading: false, error: action.message, unavailable: null};
    case 'unavailable':
      return {...state, loading: false, error: null, unavailable: action.message};
    case 'retry':
      return {...state, error: null, loading: true};
    case 'reset':
      // Drop the whole conversation back to the empty initial state.
      return initialState;
    default:
      return state;
  }
}

let idCounter = 0;
export function createId(): string {
  idCounter += 1;
  return `m${idCounter}`;
}

/**
 * Advance the id counter past any `m<n>` ids in a restored transcript. The
 * counter is module state that resets on every page load, so without this a
 * restored transcript (m1, m2, …) would collide with freshly minted ids —
 * duplicate React keys in the message list.
 */
function seedIdCounter(messages: DisplayMessage[]): void {
  for (const message of messages) {
    const numeric = Number(message.id.slice(1));
    if (message.id.startsWith('m') && Number.isInteger(numeric) && numeric > idCounter) {
      idCounter = numeric;
    }
  }
}

/** Map display messages to the wire format, keeping the last N turns. */
export function toHistory(messages: DisplayMessage[]): AssistantChatMessage[] {
  return messages.slice(-MAX_HISTORY_TURNS).map(({role, content}) => ({role, content}));
}
