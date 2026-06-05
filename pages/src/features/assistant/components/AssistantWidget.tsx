import {useCallback, useEffect, useReducer, useState} from 'react';

import {
  DEFAULT_ASSISTANT_CONFIG,
  fetchAssistantConfig,
  sendAssistantMessage,
  type AssistantChatMessage,
  type AssistantConfig,
} from '@/features/assistant/api';

import {MessageInput} from './MessageInput';
import {MessageList} from './MessageList';
import type {DisplayMessage} from './types';

import './AssistantWidget.css';

/** Max conversation turns sent to the backend (keeps payloads bounded). */
const MAX_HISTORY_TURNS = 10;

interface ChatState {
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
  | {type: 'retry'};

const initialState: ChatState = {messages: [], loading: false, error: null, unavailable: null};

function chatReducer(state: ChatState, action: ChatAction): ChatState {
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
    default:
      return state;
  }
}

let idCounter = 0;
function createId(): string {
  idCounter += 1;
  return `m${idCounter}`;
}

/** Map display messages to the wire format, keeping the last N turns. */
function toHistory(messages: DisplayMessage[]): AssistantChatMessage[] {
  return messages.slice(-MAX_HISTORY_TURNS).map(({role, content}) => ({role, content}));
}

const ChatIcon = () => (
  <svg className="itg-assistant__launcher-icon" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H8l-5 4V6a2 2 0 0 1 1-2z" />
  </svg>
);

/**
 * Public floating chat assistant. Mounts as an independent React root; does not
 * depend on the router or app auth providers.
 */
export function AssistantWidget() {
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState<AssistantConfig>(DEFAULT_ASSISTANT_CONFIG);
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const [lastAttempt, setLastAttempt] = useState<string | null>(null);

  // Fetch config once; fall back to hardcoded defaults if the request fails.
  useEffect(() => {
    let cancelled = false;
    fetchAssistantConfig()
      .then((cfg) => {
        if (!cancelled) setConfig(cfg);
      })
      .catch(() => {
        /* keep DEFAULT_ASSISTANT_CONFIG */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const disabled = !config.enabled || state.unavailable !== null;
  const unavailableMessage = !config.enabled ? config.unavailable_message : state.unavailable;

  // Call the backend with `text` as the new message and `priorTurns` as the
  // transcript BEFORE it. `text` is sent only as `message`, never duplicated
  // into `history`.
  const runChat = useCallback(async (text: string, priorTurns: DisplayMessage[]) => {
    const result = await sendAssistantMessage(text, toHistory(priorTurns));
    switch (result.status) {
      case 'ok':
        dispatch({type: 'reply', message: {id: createId(), role: 'assistant', content: result.reply}});
        break;
      case 'unavailable':
        dispatch({type: 'unavailable', message: result.message});
        break;
      case 'budget':
      case 'error':
        dispatch({type: 'error', message: result.message});
        break;
    }
  }, []);

  const send = useCallback(
    async (text: string) => {
      if (disabled) return;
      // Prior turns are the transcript snapshot before this message is appended.
      const priorTurns = state.messages;
      setLastAttempt(text);
      dispatch({type: 'send', message: {id: createId(), role: 'user', content: text}});
      await runChat(text, priorTurns);
    },
    [disabled, runChat, state.messages],
  );

  const handleRetry = useCallback(() => {
    if (lastAttempt === null) return;
    // The failed user message is already in the transcript; re-send it without
    // re-appending. Prior turns exclude that trailing user turn.
    dispatch({type: 'retry'});
    void runChat(lastAttempt, state.messages.slice(0, -1));
  }, [lastAttempt, runChat, state.messages]);

  const showStarters = state.messages.length === 0 && config.starter_questions.length > 0;

  return (
    <div className="itg-assistant">
      {open && (
        <div className="itg-assistant__panel" role="dialog" aria-label="Chat assistant" aria-modal="false">
          <div className="itg-assistant__header">
            <h2 className="itg-assistant__title">Ask Innovate to Grow</h2>
            <button
              type="button"
              className="itg-assistant__close"
              aria-label="Close chat assistant"
              onClick={() => setOpen(false)}
            >
              ×
            </button>
          </div>

          {disabled ? (
            <div className="itg-assistant__messages">
              <div className="itg-assistant__unavailable" role="status">
                {/* On the disabled branch unavailableMessage is always set:
                    either config.unavailable_message (!enabled) or state.unavailable. */}
                {unavailableMessage ?? config.unavailable_message}
              </div>
            </div>
          ) : (
            <MessageList
              welcomeMessage={config.welcome_message}
              messages={state.messages}
              starterQuestions={config.starter_questions}
              showStarters={showStarters}
              loading={state.loading}
              error={state.error}
              startersDisabled={state.loading}
              onStarterSelect={(question) => void send(question)}
              onRetry={handleRetry}
            />
          )}

          <MessageInput
            maxChars={config.max_message_chars}
            disabled={disabled || state.loading}
            onSend={(text) => void send(text)}
          />
        </div>
      )}

      <button
        type="button"
        className="itg-assistant__launcher"
        aria-label="Open chat assistant"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <ChatIcon />
      </button>
    </div>
  );
}
