export type SendVerificationOperation =
  | 'email_auth.request_code'
  | 'phone_auth.request_code'
  | 'login.request_code'
  | 'register'
  | 'register.resend_code'
  | 'password_reset.request_code'
  | 'change_password.request_code'
  | 'delete_account.request_code'
  | 'contact_email.create'
  | 'contact_email.request_verification'
  | 'contact_phone.request_verification'
  | 'event.send_phone_code'
  | 'admin.login.request_code'
  | 'admin.login.remembered_code'
  | 'admin.login.resend';

export type DestinationKind = 'email' | 'phone';

export interface SendVerificationFields {
  verification_challenge_id: string;
  verification_payload: string;
  send_request_id: string;
}

export interface ChallengeResponse {
  challenge_id: string;
  expires_at: string;
  algorithm: string;
  cost: number;
  challenge: Record<string, unknown>;
}

export interface SendRequestStatus {
  request_id: string;
  status: 'pending' | 'sending' | 'provider_accepted' | 'definitely_failed' | 'unknown' | 'submitted';
  http_status: number;
  code: string | null;
  result: Record<string, unknown>;
  challenge_id: string | null;
}

export type VerifiedSendPhase = 'idle' | 'challenging' | 'solving' | 'sending' | 'error';

export interface VerifiedSendStatus {
  phase: VerifiedSendPhase;
  message: string;
}
