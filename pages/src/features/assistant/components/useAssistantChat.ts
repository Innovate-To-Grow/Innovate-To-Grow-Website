import {useCallback, useEffect, useReducer, useRef, useState} from 'react';

import {sendAssistantMessage} from '@/features/assistant/api';

import {clearConversation, getSessionId, saveTranscript} from '../utils/sessionStore';
import {chatReducer, createId, initState, toHistory} from './chatState';
import type {DisplayMessage} from './types';

/**
 * The conversation: its transcript (persisted for the session), sending, retrying the last failed
 * message, and starting over. ``configEnabled`` is the assistant config's switch.
 */
export function useAssistantChat(configEnabled: boolean) {
  const [state, dispatch] = useReducer(chatReducer, undefined, initState);
  const [lastAttempt, setLastAttempt] = useState<string | null>(null);
  // Opaque per-conversation id; minted/restored on mount and rotated on reset.
  const sessionIdRef = useRef<string>(getSessionId());
  // Bumped on "New conversation" so a reply from a request that was still in
  // flight when the user reset never lands in the fresh conversation.
  const generationRef = useRef(0);

  // Persist the transcript on every change so a page reload restores it. The
  // empty case is persisted too, so "New conversation" clears across reloads.
  useEffect(() => {
    saveTranscript(state.messages);
  }, [state.messages]);

  const disabled = !configEnabled || state.unavailable !== null;

  // Call the backend with `text` as the new message and `priorTurns` as the
  // transcript BEFORE it. `text` is sent only as `message`, never duplicated
  // into `history`.
  const runChat = useCallback(async (text: string, priorTurns: DisplayMessage[]) => {
    const generation = generationRef.current;
    const result = await sendAssistantMessage(text, toHistory(priorTurns), sessionIdRef.current);
    // The conversation was reset while this request was in flight: drop it.
    if (generation !== generationRef.current) return;
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

  const handleNewConversation = useCallback(() => {
    // Drop the stored transcript + rotate to a fresh session id, then reset the
    // in-memory state and any pending retry.
    clearConversation();
    sessionIdRef.current = getSessionId();
    generationRef.current += 1;
    dispatch({type: 'reset'});
    setLastAttempt(null);
  }, []);

  return {state, disabled, send, handleRetry, handleNewConversation};
}
