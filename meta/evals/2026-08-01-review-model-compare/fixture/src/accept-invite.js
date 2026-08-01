import { getInvite, saveInvite, addMember, getMember } from './store.js'
import { record } from './audit.js'

export async function acceptInvite(req) {
  const { token, userId, role } = req.body

  const invite = await getInvite(token)
  if (!invite) {
    return { status: 404, body: { error: 'invite not found' } }
  }

  const now = Date.now()
  if (invite.expiresAt < now) {
    return { status: 410, body: { error: 'invite expired' } }
  }

  if (invite.usedAt) {
    return { status: 409, body: { error: 'invite already used' } }
  }

  const existing = await getMember(invite.teamId, userId)
  if (existing) {
    return { status: 409, body: { error: 'already a member' } }
  }

  const member = await addMember(invite.teamId, userId, role ?? invite.role)

  invite.usedAt = new Date().toISOString()
  saveInvite(invite)

  await record('invite.accepted', { teamId: invite.teamId, userId })

  return { status: 200, body: { member } }
}

export async function expireStaleInvites(tokens) {
  const expired = []
  for (const t of tokens) {
    const inv = await getInvite(t)
    if (!inv) continue
    inv.expiresAt = 0
    await saveInvite(inv)
    expired.push(t)
  }
  return expired
}
