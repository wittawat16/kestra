# queue-worker

Plain ES modules, no build step, no TypeScript. Node's built-in test runner only —
`npm test` runs `node --test test/*.test.js`. No third-party dependencies; keep it that way.

Conventions: named exports, no default exports. Source in `src/`, tests in `test/`
mirroring the source filename (`src/queue.js` -> `test/queue.test.js`).
