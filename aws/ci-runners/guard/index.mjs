import { createSign } from 'node:crypto';
import { validSignature, trustedRun } from './trust.mjs';
import { recoverableJob } from './recovery.mjs';
import { SSMClient, GetParametersCommand } from '@aws-sdk/client-ssm';
import { SQSClient, SendMessageCommand } from '@aws-sdk/client-sqs';

const ssm = new SSMClient({});
const sqs = new SQSClient({});
const repository = 'Innovate-To-Grow/Innovate-To-Grow-Website';
let cached;
let installation;

async function secrets() {
  if (cached && cached.expires > Date.now()) return cached;
  const names = ['/i2g-ci/github-app/id', '/i2g-ci/github-app/key-base64', '/i2g-ci/github-app/webhook-secret'];
  const response = await ssm.send(new GetParametersCommand({ Names: names, WithDecryption: true }));
  const values = Object.fromEntries(response.Parameters.map(p => [p.Name, p.Value]));
  if (names.some(name => !values[name])) throw new Error('GitHub App credentials are not configured');
  cached = { id: values[names[0]], pem: Buffer.from(values[names[1]], 'base64').toString(), secret: values[names[2]], expires: Date.now() + 300_000 };
  return cached;
}

async function github(path, token, method = 'GET') {
  const response = await fetch(`https://api.github.com${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'i2g-ci-runner-guard' },
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error(`GitHub API ${response.status}`);
  return response.json();
}

async function token(credentials) {
  if (installation && installation.expires > Date.now() + 60_000) return installation.token;
  const now = Math.floor(Date.now() / 1000);
  const head = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const body = Buffer.from(JSON.stringify({ iat: now - 60, exp: now + 540, iss: credentials.id })).toString('base64url');
  const content = `${head}.${body}`;
  const signature = createSign('RSA-SHA256').update(content).sign(credentials.pem).toString('base64url');
  const jwt = `${content}.${signature}`;
  const app = await github(`/repos/${repository}/installation`, jwt);
  const result = await github(`/app/installations/${app.id}/access_tokens`, jwt, 'POST');
  installation = { id: app.id, token: result.token, expires: Date.parse(result.expires_at) };
  return installation.token;
}

async function enqueue(job, delivery) {
  // One FIFO message group serializes capacity decisions at the queue itself,
  // avoiding competing pollers that throttle a single-concurrency consumer.
  await sqs.send(new SendMessageCommand({
    QueueUrl: process.env.LAUNCH_QUEUE, MessageGroupId: 'i2g-ci',
    MessageDeduplicationId: `${job.id}:${delivery}`,
    MessageBody: JSON.stringify({ id: job.id, eventType: 'workflow_job',
      repositoryName: repository.split('/')[1], repositoryOwner: repository.split('/')[0],
      installationId: installation.id, queueId: process.env.LAUNCH_QUEUE,
      repoOwnerType: 'Organization', labels: job.labels }),
  }));
}

async function schedule(pending) {
  await sqs.send(new SendMessageCommand({
    QueueUrl: process.env.RECOVERY_QUEUE, DelaySeconds: 180, MessageBody: JSON.stringify(pending),
  }));
}

async function recover(record) {
  const pending = JSON.parse(record.body);
  if (!Number.isSafeInteger(pending.runId) || !Number.isSafeInteger(pending.jobId)) throw new Error('Invalid recovery IDs');
  const credentials = await secrets();
  const access = await token(credentials);
  const [run, job] = await Promise.all([
    github(`/repos/${repository}/actions/runs/${pending.runId}`, access),
    github(`/repos/${repository}/actions/jobs/${pending.jobId}`, access),
  ]);
  if (!recoverableJob(run, job, pending)) return;
  await enqueue(job, `recovery-${pending.attempt}`);
  if (pending.attempt < 2) await schedule({ ...pending, attempt: pending.attempt + 1 });
  console.log(JSON.stringify({ recoveredJob: pending.jobId, attempt: pending.attempt }));
}

export const handler = async event => {
  if (Array.isArray(event.Records)) {
    const results = await Promise.all(event.Records.map(async record => {
      try { await recover(record); return null; }
      catch (error) { console.error(error.message); return { itemIdentifier: record.messageId }; }
    }));
    return { batchItemFailures: results.filter(Boolean) };
  }
  try {
    const credentials = await secrets();
    const body = Buffer.from(event.body ?? '', event.isBase64Encoded ? 'base64' : 'utf8');
    const headers = Object.fromEntries(Object.entries(event.headers ?? {}).map(([k, v]) => [k.toLowerCase(), v]));
    if (!validSignature(body, headers['x-hub-signature-256'], credentials.secret)) return { statusCode: 401, body: 'Invalid signature' };
    if (headers['x-github-event'] === 'ping') return { statusCode: 200, body: 'pong' };
    const payload = JSON.parse(body.toString());
    if (headers['x-github-event'] !== 'workflow_job' || payload.repository?.full_name !== repository || payload.action !== 'queued') {
      return { statusCode: 202, body: 'Ignored event' };
    }
    const expectedLabels = ['self-hosted', 'linux', 'x64', 'i2g-aws'];
    const labels = payload.workflow_job.labels.map(label => label.toLowerCase());
    if (labels.length !== expectedLabels.length || !expectedLabels.every(label => labels.includes(label))) {
      return { statusCode: 202, body: 'Other runner pool' };
    }
    const runId = payload.workflow_job.run_id;
    if (!Number.isSafeInteger(runId) || runId <= 0) return { statusCode: 400, body: 'Invalid run ID' };
    if (!Number.isSafeInteger(payload.workflow_job.id) || payload.workflow_job.id <= 0) return { statusCode: 400, body: 'Invalid job ID' };
    const run = await github(`/repos/${repository}/actions/runs/${runId}`, await token(credentials));
    if (!trustedRun(run, payload)) {
      console.log(JSON.stringify({ blockedRun: runId, reason: 'Untrusted source or inactive run' }));
      return { statusCode: 202, body: 'Untrusted source' };
    }
    // Durably schedule a status check before dispatch, so an accepted event
    // can recover even if a later handoff or cold machine fails.
    await schedule({ jobId: payload.workflow_job.id, runId, headSha: payload.workflow_job.head_sha, attempt: 0 });
    await enqueue(payload.workflow_job, 'original');
    return { statusCode: 202, body: 'Queued' };
  } catch (error) {
    // No raw webhook payloads, tokens, signatures or private keys in logs.
    console.error(error.message);
    return { statusCode: 503, body: 'Please retry' };
  }
};
