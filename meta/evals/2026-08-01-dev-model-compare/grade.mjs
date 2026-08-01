// Objective grader for the meta-dev model comparison.
// Written and committed BEFORE either model ran, so the rubric can't drift to fit the output.
// Usage: node grade.mjs <dir>     (dir contains src/accept-invite.js)

const dir = process.argv[2]
if (!dir) {
  console.error('usage: node grade.mjs <dir>')
  process.exit(2)
}

const { acceptInvite } = await import(`${dir}/src/accept-invite.js`)
const store = await import(`${dir}/src/store.js`)
const audit = await import(`${dir}/src/audit.js`)

const results = []
const check = (id, desc, pass, detail) => results.push({ id, desc, pass, detail })

const fresh = (over = {}) => ({
  token: 'tok',
  teamId: 'team1',
  role: 'member',
  expiresAt: Date.now() + 86_400_000,
  ...over,
})

async function call(body) {
  try {
    return await acceptInvite({ body })
  } catch (e) {
    return { status: 'THREW', error: String(e?.message ?? e) }
  }
}

// P1 — happy path
store._reset?.()
await store.saveInvite(fresh())
let r = await call({ token: 'tok', userId: 'u1' })
check('P1', 'valid invite -> 200 + member', r.status === 200, `got ${r.status}`)

// P2 — unknown token
store._reset?.()
r = await call({ token: 'nope', userId: 'u1' })
check('P2', 'unknown token -> 404', r.status === 404, `got ${r.status}`)

// P3 — expired, stored as a NUMBER (the internal sweep form)
store._reset?.()
await store.saveInvite(fresh({ expiresAt: Date.now() - 86_400_000 }))
r = await call({ token: 'tok', userId: 'u1' })
check('P3', 'expired (numeric expiresAt) -> 410', r.status === 410, `got ${r.status}`)

// P4 — expired, stored as an ISO STRING (the invite-creation form the spec names)
store._reset?.()
await store.saveInvite(fresh({ expiresAt: new Date(Date.now() - 86_400_000).toISOString() }))
r = await call({ token: 'tok', userId: 'u1' })
check('P4', 'expired (ISO-string expiresAt) -> 410', r.status === 410, `got ${r.status}`)

// P5 — unexpired ISO string must still be accepted (guards against over-correcting P4)
store._reset?.()
await store.saveInvite(fresh({ expiresAt: new Date(Date.now() + 86_400_000).toISOString() }))
r = await call({ token: 'tok', userId: 'u1' })
check('P5', 'valid (ISO-string expiresAt) -> 200', r.status === 200, `got ${r.status}`)

// P6 — already redeemed
store._reset?.()
await store.saveInvite(fresh())
await call({ token: 'tok', userId: 'u1' })
r = await call({ token: 'tok', userId: 'u2' })
check('P6', 'already redeemed -> 409', r.status === 409, `got ${r.status}`)

// P7 — already a member
store._reset?.()
await store.saveInvite(fresh())
await store.addMember('team1', 'u1', 'member')
r = await call({ token: 'tok', userId: 'u1' })
check('P7', 'already a member -> 409', r.status === 409, `got ${r.status}`)

// P8 — caller-supplied role must not widen the invite's role
store._reset?.()
await store.saveInvite(fresh({ role: 'member' }))
await call({ token: 'tok', userId: 'u1', role: 'owner' })
let m = await store.getMember('team1', 'u1')
check('P8', 'caller role does NOT override invite role', m?.role === 'member', `granted role=${m?.role}`)

// P9 — audit entry written on success
store._reset?.()
const before = audit._entries().length
await store.saveInvite(fresh())
await call({ token: 'tok', userId: 'u1' })
const added = audit._entries().slice(before)
check('P9', 'audit entry invite.accepted written', added.some((e) => e.event === 'invite.accepted'),
  `events=${JSON.stringify(added.map((e) => e.event))}`)

// P10 — concurrent redemption must not create two members
store._reset?.()
await store.saveInvite(fresh())
const [a, b] = await Promise.all([
  call({ token: 'tok', userId: 'u1' }),
  call({ token: 'tok', userId: 'u2' }),
])
const both200 = a.status === 200 && b.status === 200
check('P10', 'concurrent accepts -> not both 200', !both200, `got ${a.status} and ${b.status}`)

const passed = results.filter((r) => r.pass).length
for (const r of results) {
  console.log(`${r.pass ? 'PASS' : 'FAIL'}  ${r.id}  ${r.desc}  (${r.detail})`)
}
console.log(`\n${passed}/${results.length} passed`)
process.exit(passed === results.length ? 0 : 1)
