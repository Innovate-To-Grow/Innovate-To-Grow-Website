import {useCallback, useState} from 'react';

import type {AssistantConfig} from '@/features/assistant/api';

import {MessageInput} from './MessageInput';
import {MessageList} from './MessageList';
import {useAssistantChat} from './useAssistantChat';
import {useAssistantConfig} from './useAssistantConfig';

import './AssistantWidget.css';

const ChatIcon = () => (
  <svg className="itg-assistant__launcher-icon" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H8l-5 4V6a2 2 0 0 1 1-2z" />
  </svg>
);

interface AssistantPanelProps {
  config: AssistantConfig;
  chat: ReturnType<typeof useAssistantChat>;
  onClose: () => void;
}

const AssistantPanel = ({config, chat, onClose}: AssistantPanelProps) => {
  const {state, disabled, send, handleRetry, handleNewConversation} = chat;
  const unavailableMessage = !config.enabled ? config.unavailable_message : state.unavailable;
  const showStarters = state.messages.length === 0 && config.starter_questions.length > 0;
  return (
    <div className="itg-assistant__panel" role="dialog" aria-label="Chat assistant" aria-modal="false">
      <div className="itg-assistant__header">
        <h2 className="itg-assistant__title">Ask Innovate to Grow</h2>
        <div className="itg-assistant__header-actions">
          <button
            type="button"
            className="itg-assistant__new"
            aria-label="Start a new conversation"
            onClick={handleNewConversation}
          >
            New
          </button>
          <button
            type="button"
            className="itg-assistant__close"
            aria-label="Close chat assistant"
            onClick={onClose}
          >
            ×
          </button>
        </div>
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
  );
};

/**
 * Public floating chat assistant. Mounts as an independent React root; does not
 * depend on the router or app auth providers.
 */
export function AssistantWidget() {
  const [open, setOpen] = useState(false);
  const config = useAssistantConfig();
  const chat = useAssistantChat(config.enabled);

  const handleOpen = useCallback(() => {
    window.dispatchEvent(new Event('i2g-assistant-interaction'));
    setOpen((prev) => !prev);
  }, []);

  return (
    <div className="itg-assistant">
      {open && <AssistantPanel config={config} chat={chat} onClose={() => setOpen(false)} />}

      <button
        type="button"
        className="itg-assistant__launcher"
        aria-label="Open chat assistant"
        aria-expanded={open}
        onClick={handleOpen}
      >
        <ChatIcon />
      </button>
    </div>
  );
}
