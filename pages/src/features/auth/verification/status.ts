import type {VerifiedSendStatus} from './types';

type Listener = (status: VerifiedSendStatus) => void;

const listeners = new Set<Listener>();
let current: VerifiedSendStatus = {phase: 'idle', message: ''};

export function getVerifiedSendStatus(): VerifiedSendStatus {
  return current;
}

export function setVerifiedSendStatus(status: VerifiedSendStatus): void {
  current = status;
  listeners.forEach((listener) => listener(status));
}

export function subscribeVerifiedSendStatus(listener: Listener): () => void {
  listeners.add(listener);
  listener(current);
  return () => {
    listeners.delete(listener);
  };
}
