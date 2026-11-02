import { createHmac, timingSafeEqual } from 'node:crypto';

const repository = 'Innovate-To-Grow/Innovate-To-Grow-Website';

export function validSignature(body, signature, secret) {
  if (typeof signature !== 'string' || !/^sha256=[a-f0-9]{64}$/.test(signature)) return false;
  const expected = `sha256=${createHmac('sha256', secret).update(body).digest('hex')}`;
  return timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
}

export function trustedRun(run, payload) {
  return run.repository?.full_name === repository && run.head_repository?.full_name === repository &&
    run.head_sha === payload.workflow_job.head_sha && run.id === payload.workflow_job.run_id &&
    ['queued', 'in_progress', 'waiting', 'requested', 'pending'].includes(run.status) &&
    run.event !== 'pull_request_target';
}
