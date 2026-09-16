import {authApi} from '../api/client';

import type {
  ChallengeResponse,
  DestinationKind,
  SendRequestStatus,
  SendVerificationOperation,
} from './types';

export async function createSendChallenge(input: {
  operation: SendVerificationOperation;
  destination?: string;
  destination_kind?: DestinationKind;
  region?: string;
  contact_id?: string;
  event_slug?: string;
  identifier?: string;
  email?: string;
  phone?: string;
  phone_number?: string;
}, signal?: AbortSignal): Promise<ChallengeResponse> {
  const response = await authApi.post<ChallengeResponse>(
    '/authn/send-verification/challenge/',
    input,
    {signal, timeout: 15_000, withCredentials: true},
  );
  return response.data;
}

export async function fetchSendRequestStatus(requestId: string): Promise<SendRequestStatus> {
  const response = await authApi.get<SendRequestStatus>(
    `/authn/send-verification/requests/${requestId}/`,
    {timeout: 10_000, withCredentials: true},
  );
  return response.data;
}
