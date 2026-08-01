import { renderPage } from './layout.js'
import { lookupRates } from '../catalog/rates.js'

export async function catalogPage(req) {
  const rates = await lookupRates(req.query.skus ?? [], req.query.currency ?? 'USD')
  const rows = rates.map((r) => `<tr><td>${r.sku}</td><td>${r.amount}</td></tr>`).join('')
  return { status: 200, body: renderPage('Catalog', `<table>${rows}</table>`) }
}
