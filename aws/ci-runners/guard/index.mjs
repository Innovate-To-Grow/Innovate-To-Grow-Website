import { createSign } from 'node:crypto';
import { validSignature, trustedRun } from './trust.mjs';
import { SSMClient, GetParametersCommand } from '@aws-sdk/client-ssm';
import { LambdaClient, InvokeCommand } from '@aws-sdk/client-lambda';

const ssm = new SSMClient({});
const lambda = new LambdaClient({});
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
  installation = { token: result.token, expires: Date.parse(result.expires_at) };
  return installation.token;
}

export const handler = async event => {
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
    const run = await github(`/repos/${repository}/actions/runs/${runId}`, await token(credentials));
    if (!trustedRun(run, payload)) {
      console.log(JSON.stringify({ blockedRun: runId, reason: 'Untrusted source or inactive run' }));
      return { statusCode: 202, body: 'Untrusted source' };
    }
    // Preserve the signed raw body; the upstream webhook verifies it again.
    const forwarded = { ...event, body: body.toString(), isBase64Encoded: false };
    const invoked = await lambda.send(new InvokeCommand({
      FunctionName: process.env.WEBHOOK_FUNCTION, InvocationType: 'RequestResponse', Payload: Buffer.from(JSON.stringify(forwarded)),
    }));
    if (invoked.FunctionError) throw new Error('Runner webhook failed');
    const result = JSON.parse(Buffer.from(invoked.Payload).toString());
    if (result.statusCode >= 300) throw new Error(`Runner webhook returned ${result.statusCode}`);
    return { statusCode: 202, body: 'Queued' };
  } catch (error) {
    // No raw webhook payloads, tokens, signatures or private keys in logs.
    console.error(error.message);
    return { statusCode: 503, body: 'Please retry' };
  }
};
