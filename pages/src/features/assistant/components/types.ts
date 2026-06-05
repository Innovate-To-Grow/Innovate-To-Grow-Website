/** A chat turn as rendered in the message list. */
export interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}
