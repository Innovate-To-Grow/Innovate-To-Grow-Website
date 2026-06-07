import {useEffect, useRef} from 'react';

import {MarkdownMessage} from './MarkdownMessage';
import {StarterQuestions} from './StarterQuestions';
import type {DisplayMessage} from './types';

interface MessageListProps {
  welcomeMessage: string;
  messages: DisplayMessage[];
  starterQuestions: string[];
  showStarters: boolean;
  loading: boolean;
  error: string | null;
  startersDisabled: boolean;
  onStarterSelect: (question: string) => void;
  onRetry: () => void;
}

/** Scrollable transcript: welcome message, starters, bubbles, loading + error. */
export function MessageList({
  welcomeMessage,
  messages,
  starterQuestions,
  showStarters,
  loading,
  error,
  startersDisabled,
  onStarterSelect,
  onRetry,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  // Keep the latest content in view as messages, loading, and errors change.
  // scrollIntoView is unimplemented in jsdom, so guard before calling.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({block: 'end'});
  }, [messages, loading, error]);

  return (
    <div className="itg-assistant__messages" role="log" aria-live="polite" aria-label="Conversation">
      <div className="itg-assistant__bubble itg-assistant__bubble--assistant itg-assistant__bubble--welcome">
        {welcomeMessage}
      </div>

      {showStarters && (
        <StarterQuestions questions={starterQuestions} disabled={startersDisabled} onSelect={onStarterSelect} />
      )}

      {messages.map((message) => (
        <div
          key={message.id}
          data-message-id={message.id}
          className={`itg-assistant__bubble itg-assistant__bubble--${message.role}`}
        >
          {/* Assistant replies are Markdown; user input stays inert plain text. */}
          {message.role === 'assistant' ? <MarkdownMessage content={message.content} /> : message.content}
        </div>
      ))}

      {loading && (
        <div className="itg-assistant__loading" aria-label="Assistant is typing">
          <span className="itg-assistant__loading-dot" />
          <span className="itg-assistant__loading-dot" />
          <span className="itg-assistant__loading-dot" />
        </div>
      )}

      {error && (
        <div className="itg-assistant__error" role="alert">
          <div>{error}</div>
          <button type="button" className="itg-assistant__retry" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}

      <div ref={endRef} />
    </div>
  );
}
