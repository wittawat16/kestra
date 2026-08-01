# storefront

Node ESM service. No design system — admin pages are plain server-rendered HTML with inline styles.

## Conventions
* Every outbound HTTP call goes through `src/lib/http.js` — never call `undici` or `fetch` directly.
* Handlers return `{ status, body }`; they never write to a response object.
* Admin pages live under `src/admin/` and are rendered by `renderPage()` in `src/admin/layout.js`.
