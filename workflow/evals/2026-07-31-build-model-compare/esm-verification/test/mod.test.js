import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existing, notThere } from '../src/mod.js';

test('a passing test that does not use notThere', () => {
  assert.equal(existing(), 1);
});

test('a test that references notThere', () => {
  assert.equal(typeof notThere, 'function');
});
