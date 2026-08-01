import { request } from '../lib/http.js'

const PRICING_URL = process.env.PRICING_SERVICE_URL

export async function lookupRate(sku, currency) {
  const res = await request(`${PRICING_URL}/rates`, { query: { sku, currency } })
  if (res.status !== 200) {
    throw new Error(`pricing lookup failed: ${res.status}`)
  }
  return res.body
}

export async function lookupRates(skus, currency) {
  return Promise.all(skus.map((s) => lookupRate(s, currency)))
}
