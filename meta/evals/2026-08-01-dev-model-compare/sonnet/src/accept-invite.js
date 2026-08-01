import { getInvite, saveInvite, addMember, getMember } from './store.js'
import { record } from './audit.js'

const tokenLocks = new Map()

function withTokenLock(token, fn) {
  const prior = tokenLocks.get(token) ?? Promise.resolve()
  const settled = prior.then(fn, fn)
  tokenLocks.set(token, settled.then(() => {}, () => {}))
  return settled
}

function isExpired(expiresAt) {
  const expiryMs = typeof expiresAt === 'number' ? expiresAt : Date.parse(expiresAt)
  return Date.now() > expiryMs
}

export async function acceptInvite(token, userId) {
  return withTokenLock(token, async () => {
    const invite = await getInvite(token)
    if (!invite) {
      return { status: 404, body: { error: 'invite not found' } }
    }

    if (isExpired(invite.expiresAt)) {
      return { status: 410, body: { error: 'invite expired' } }
    }

    if (invite.redeemedAt) {
      return { status: 409, body: { error: 'invite already redeemed' } }
    }

    const existingMember = await getMember(invite.teamId, userId)
    if (existingMember) {
      return { status: 409, body: { error: 'already a member of this team' } }
    }

    await saveInvite({ ...invite, redeemedAt: new Date().toISOString() })
    const member = await addMember(invite.teamId, userId, invite.role)

    try {
      await record('invite.accepted', { token, teamId: invite.teamId, userId, role: invite.role })
    } catch {
      // audit log is not a transactional participant — membership above already stands
    }

    return { status: 200, body: member }
  })
}
