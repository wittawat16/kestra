import { getInvite, saveInvite, addMember, getMember } from './store.js'
import { record } from './audit.js'

function isExpired(expiresAt, now) {
  const at = new Date(expiresAt).getTime()
  return Number.isNaN(at) || at <= now
}

export async function acceptInvite({ token, userId }) {
  const invite = await getInvite(token)
  if (!invite) return { status: 404, body: { error: 'invite_not_found' } }

  if (invite.redeemedAt) return { status: 409, body: { error: 'invite_already_redeemed' } }

  if (isExpired(invite.expiresAt, Date.now())) {
    return { status: 410, body: { error: 'invite_expired' } }
  }

  // Claim before the next await: getInvite hands back the stored object, so marking it here is
  // what stops a concurrent accept of the same token from getting past the check above.
  invite.redeemedAt = new Date().toISOString()
  invite.redeemedBy = userId
  await saveInvite(invite)

  const existing = await getMember(invite.teamId, userId)
  if (existing) return { status: 409, body: { error: 'already_a_member' } }

  const member = await addMember(invite.teamId, userId, invite.role)

  try {
    await record('invite.accepted', { token, teamId: invite.teamId, userId, role: invite.role })
  } catch {
    // Membership stands regardless — the audit log is not a transactional participant.
  }

  return { status: 200, body: member }
}
