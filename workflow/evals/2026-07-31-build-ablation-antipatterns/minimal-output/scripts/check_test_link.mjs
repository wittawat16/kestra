#!/usr/bin/env node
// Link-only static check for a not-yet-implemented ESM test file.
//
// Why this exists: `node --check` only parses syntax — it does not resolve
// any import binding, so a test file that imports a misspelled/nonexistent
// export from the implementation module still exits 0. Actually *importing*
// the test file for real fails for the wrong reason before implementation
// exists (Node's ESM loader throws "does not provide an export named ..."
// for whatever hasn't been implemented yet), which would make this check
// permanently red pre-implementation — the opposite of what a generate-tests
// polarity check needs (it must PASS before implementation exists).
//
// This script uses vm.SourceTextModule to LINK (resolve import bindings)
// the test file against a synthetic stand-in for the implementation module
// that declares only the names it is committed to exporting (per the spec's
// Functional Requirements / Files-to-Touch), without executing the real
// implementation OR any test body. Node's module linker resolves imported
// names during `link()`, before any evaluation — so this genuinely proves
// "every name imported from the implementation module is one the spec
// commits to" without requiring the implementation, or the test bodies, to
// run.
//
// Known limitation (stated, not hidden): this does not catch a bare
// undefined identifier referenced *inside* a test body (e.g. a typo'd local
// variable) — that is a runtime ReferenceError in JS with no static check
// available in vanilla Node (no AST/scope-analysis API, and this project's
// CLAUDE.md forbids adding a linter as a third-party dependency). That
// residual class of bug is still caught later: `implement`'s own build
// sanity pass and `verify`'s real `npm test` run both execute the test
// bodies for real.
//
// Usage:
//   node --experimental-vm-modules check_test_link.mjs <test-file> <comma,separated,expected,exports> [<module-specifier-substring>]
//
// Exit 0 and prints LINK_OK on success. Exit 1 and prints LINK_FAIL: <reason>
// otherwise (syntax error, or an import name not in the expected-exports list).

import vm from 'node:vm';
import fs from 'node:fs';

const [, , testFile, exportsArg, specifierSubstring = 'queue.js'] = process.argv;

if (!testFile || !exportsArg) {
  console.error('usage: check_test_link.mjs <test-file> <comma,separated,expected,exports> [module-specifier-substring]');
  process.exit(2);
}

const stubExportNames = exportsArg.split(',').map((s) => s.trim()).filter(Boolean);

let src;
try {
  src = fs.readFileSync(testFile, 'utf8');
} catch (e) {
  console.error(`LINK_FAIL: cannot read ${testFile}: ${e.message}`);
  process.exit(1);
}

let testMod;
try {
  testMod = new vm.SourceTextModule(src, { identifier: testFile });
} catch (e) {
  // Syntax error — subsumes what `node --check` would have caught.
  console.error(`LINK_FAIL: syntax error in ${testFile}: ${e.message}`);
  process.exit(1);
}

async function linker(specifier) {
  if (specifier.includes(specifierSubstring)) {
    // Synthetic stand-in for the not-yet-(fully-)implemented module: declares
    // only the names the spec commits to exporting. Linking against this,
    // rather than the real file, is what makes the check pass pre-implementation.
    return new vm.SyntheticModule(
      stubExportNames,
      function () {
        for (const name of stubExportNames) this.setExport(name, function stub() {});
      },
      { identifier: `stub:${specifier}` },
    );
  }
  // Everything else (node:test, node:assert/strict, ...) is real and already
  // available in this process — wrap its real exports as a synthetic module
  // so the linker has something to hand back without evaluating the test file.
  const mod = await import(specifier);
  const exportNames = Object.keys(mod);
  return new vm.SyntheticModule(
    exportNames,
    function () {
      for (const name of exportNames) this.setExport(name, mod[name]);
    },
    { identifier: `${specifier}#real` },
  );
}

try {
  await testMod.link(linker);
  console.log(`LINK_OK: ${testFile} — every import binding resolves to a committed export (or a real built-in); no test code executed.`);
  process.exit(0);
} catch (e) {
  console.error(`LINK_FAIL: ${e.message}`);
  process.exit(1);
}
