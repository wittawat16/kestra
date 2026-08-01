export function renderPage(title, inner) {
  return `<!doctype html><title>${title}</title><main style="font-family:system-ui;padding:2rem">${inner}</main>`
}
