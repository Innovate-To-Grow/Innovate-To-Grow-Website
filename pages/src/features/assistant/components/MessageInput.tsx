import {useState, type KeyboardEvent} from 'react';

interface MessageInputProps {
  maxChars: number;
  disabled: boolean;
  onSend: (message: string) => void;
}

/** Text entry row with char counter, Enter-to-send, and a send button. */
export function MessageInput({maxChars, disabled, onSend}: MessageInputProps) {
  const [value, setValue] = useState('');

  // A non-positive cap means "no limit" (matches the backend serializer).
  const hasLimit = maxChars > 0;
  const trimmed = value.trim();
  const overLimit = hasLimit && value.length > maxChars;
  const canSend = !disabled && trimmed.length > 0 && !overLimit;

  const submit = () => {
    if (!canSend) return;
    onSend(trimmed);
    setValue('');
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Ignore Enter while an IME composition is in progress (CJK input): that
    // Enter confirms the candidate text, it must not submit the message.
    if (event.nativeEvent.isComposing) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="itg-assistant__input-row">
      <div className="itg-assistant__input-controls">
        <textarea
          className="itg-assistant__textarea"
          rows={1}
          value={value}
          disabled={disabled}
          placeholder={disabled ? 'Assistant unavailable' : 'Type your message…'}
          aria-label="Message"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button type="button" className="itg-assistant__send" disabled={!canSend} onClick={submit}>
          Send
        </button>
      </div>
      {hasLimit && (
        <span className={`itg-assistant__counter${overLimit ? ' itg-assistant__counter--over' : ''}`}>
          {value.length}/{maxChars}
        </span>
      )}
    </div>
  );
}
