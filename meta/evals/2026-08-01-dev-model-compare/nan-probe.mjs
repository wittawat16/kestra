const dir = process.argv[2]
const { acceptInvite } = await import(`${dir}/src/accept-invite.js`)
const store = await import(`${dir}/src/store.js`)
const convs = [
  (b) => acceptInvite({ body: b }), (b) => acceptInvite(b), (b) => acceptInvite(b.token, b.userId, b.role),
]
let call
for (const c of convs) {
  store._reset?.()
  await store.saveInvite({ token: 'p', teamId: 't', role: 'member', expiresAt: Date.now() + 8.64e7 })
  try { if ((await c({ token: 'p', userId: 'u' }))?.status === 200) { call = c; break } } catch {}
}
for (const bad of ['not-a-date', undefined, null, {}]) {
  store._reset?.()
  await store.saveInvite({ token: 'p', teamId: 't', role: 'member', expiresAt: bad })
  let r; try { r = await call({ token: 'p', userId: 'u' }) } catch (e) { r = { status: 'THREW' } }
  const open = r.status === 200
  console.log(`  expiresAt=${JSON.stringify(bad)} -> ${r.status} ${open ? '❌ FAILS OPEN (invite honored)' : '✅ refused'}`)
}
