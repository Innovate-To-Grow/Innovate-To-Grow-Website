import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import test from 'node:test';
import { validSignature, trustedRun } from './trust.mjs';
import { recoverableJob } from './recovery.mjs';

const repo = 'Innovate-To-Grow/Innovate-To-Grow-Website';
const payload = { workflow_job: { run_id: 123, head_sha: 'a'.repeat(40) } };
const run = { id: 123, head_sha: 'a'.repeat(40), repository: { full_name: repo }, head_repository: { full_name: repo }, status: 'in_progress', event: 'pull_request' };

test('only authentic, untampered GitHub bodies pass signature validation', () => {
  const body = Buffer.from('{"action":"queued"}');
  const signature = `sha256=${createHmac('sha256', 'test-secret').update(body).digest('hex')}`;
  assert.equal(validSignature(body, signature, 'test-secret'), true);
  assert.equal(validSignature(Buffer.from('{"action":"completed"}'), signature, 'test-secret'), false);
  assert.equal(validSignature(body, signature, 'wrong-secret'), false);
  for (const invalid of [undefined, '', 'sha256=' + 'é'.repeat(64), 'sha256=' + '0'.repeat(64)]) {
    assert.equal(validSignature(body, invalid, 'test-secret'), false);
  }
});

test('internal branches can request runners', () => assert.equal(trustedRun(run, payload), true));

test('forks cannot launch AWS machines even if they change workflow labels', () => {
  assert.equal(trustedRun({ ...run, head_repository: { full_name: 'outside/fork' } }, payload), false);
  assert.equal(trustedRun({ ...run, head_repository: null }, payload), false);
  assert.equal(trustedRun({ ...run, repository: { full_name: 'outside/fork' } }, payload), false);
});

test('mismatched, completed and privileged PR-target runs are rejected', () => {
  for (const override of [{ head_sha: 'b'.repeat(40) }, { id: 124 }, { status: 'completed' }, { status: undefined }, { event: 'pull_request_target' }]) {
    assert.equal(trustedRun({ ...run, ...override }, payload), false);
  }
});

const pending = { jobId: 456, runId: 123, headSha: run.head_sha, attempt: 0 };
const job = { id: 456, run_id: 123, head_sha: run.head_sha, status: 'queued', labels: ['self-hosted', 'Linux', 'X64', 'i2g-aws'] };

test('a lost launch can be recovered only while its original job is queued', () => {
  assert.equal(recoverableJob(run, job, pending), true);
  for (const status of ['in_progress', 'completed', 'waiting']) {
    assert.equal(recoverableJob(run, { ...job, status }, pending), false);
  }
});

test('recovery cannot cross repository, commit, job, or runner-pool boundaries', () => {
  assert.equal(recoverableJob({ ...run, head_repository: { full_name: 'outside/fork' } }, job, pending), false);
  assert.equal(recoverableJob({ ...run, status: 'completed' }, job, pending), false);
  assert.equal(recoverableJob({ ...run, event: 'pull_request_target' }, job, pending), false);
  for (const override of [{ id: 457 }, { run_id: 124 }, { head_sha: 'b'.repeat(40) }, { labels: ['self-hosted', 'Linux', 'X64', 'another-pool'] }]) {
    assert.equal(recoverableJob(run, { ...job, ...override }, pending), false);
  }
});

test('recovery is bounded and rejects malformed queue identifiers', () => {
  assert.equal(recoverableJob(run, job, { ...pending, attempt: 2 }), true);
  for (const override of [{ attempt: 3 }, { attempt: -1 }, { attempt: 0.5 }, { jobId: '456' }, { runId: '123' }]) {
    assert.equal(recoverableJob(run, job, { ...pending, ...override }), false);
  }
});
