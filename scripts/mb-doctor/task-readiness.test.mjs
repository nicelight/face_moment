import assert from 'node:assert/strict';
import test from 'node:test';

import { sddSpecFilesystemPath } from './task-readiness.mjs';

test('SDD filesystem checks ignore Markdown fragments', () => {
  assert.equal(
    sddSpecFilesystemPath(
      '.memory-bank/contracts/photo-admission-api.md#photo-upload-endpoint'
    ),
    '.memory-bank/contracts/photo-admission-api.md'
  );
});

test('SDD filesystem checks preserve unanchored paths', () => {
  assert.equal(
    sddSpecFilesystemPath('.memory-bank/domains/photo-admission.md'),
    '.memory-bank/domains/photo-admission.md'
  );
});
