'use strict';

const test = require('node:test');
const assert = require('node:assert');
const slugify = require('./slugify');

test('lowercases the input and joins words with hyphens', () => {
  assert.strictEqual(slugify('Hello World'), 'hello-world');
  assert.strictEqual(slugify('MixedCase Title Here'), 'mixedcase-title-here');
});

test('replaces punctuation with hyphens', () => {
  assert.strictEqual(slugify('Hello, World!'), 'hello-world');
  assert.strictEqual(slugify('Version 2.0 — Released!'), 'version-2-0-released');
});

test('collapses runs of separators into one hyphen', () => {
  assert.strictEqual(slugify('Hello--World'), 'hello-world');
  assert.strictEqual(slugify('Hello   World'), 'hello-world');
  assert.strictEqual(slugify('Hello - World'), 'hello-world');
});

test('strips leading and trailing hyphens', () => {
  assert.strictEqual(slugify('-hello-'), 'hello');
  assert.strictEqual(slugify('  Leading and trailing  '), 'leading-and-trailing');
  assert.strictEqual(slugify('!!!wow!!!'), 'wow');
});

test('keeps digits', () => {
  assert.strictEqual(slugify('Version 2 Released'), 'version-2-released');
});

test('handles empty and non-string input', () => {
  assert.strictEqual(slugify(''), '');
  assert.strictEqual(slugify(42), '42');
});