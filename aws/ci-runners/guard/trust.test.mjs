import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import test from 'node:test';
import { validSignature, trustedRun } from './trust.mjs';

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
