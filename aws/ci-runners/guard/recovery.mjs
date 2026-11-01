import { trustedRun } from './trust.mjs';

// Only authoritative, still-queued jobs from the originally verified commit
// may be delivered again. Never retry jobs that have started or completed.
export function recoverableJob(run, job, pending) {
  const labels = job.labels?.map(label => label.toLowerCase()) ?? [];
  const required = ['self-hosted', 'linux', 'x64', 'i2g-aws'];
  return Number.isSafeInteger(pending.jobId) && pending.jobId > 0
    && Number.isSafeInteger(pending.runId) && pending.runId > 0
    && Number.isInteger(pending.attempt) && pending.attempt >= 0 && pending.attempt < 3
    && job.id === pending.jobId && job.run_id === pending.runId
    && job.head_sha === pending.headSha && job.status === 'queued'
    && labels.length === required.length && required.every(label => labels.includes(label))
    && trustedRun(run, {
      repository: { full_name: 'Innovate-To-Grow/Innovate-To-Grow-Website' },
      workflow_job: { run_id: pending.runId, head_sha: pending.headSha },
    });
}
