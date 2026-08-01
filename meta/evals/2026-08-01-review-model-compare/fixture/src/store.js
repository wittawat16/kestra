const invites = new Map()
const members = new Map()

export async function getInvite(token) {
  return invites.get(token) ?? null
}

export async function saveInvite(invite) {
  invites.set(invite.token, invite)
}

export async function addMember(teamId, userId, role) {
  const key = `${teamId}:${userId}`
  members.set(key, { teamId, userId, role, joinedAt: new Date().toISOString() })
  return members.get(key)
}

export async function getMember(teamId, userId) {
  return members.get(`${teamId}:${userId}`) ?? null
}

export function _reset() {
  invites.clear()
  members.clear()
}
