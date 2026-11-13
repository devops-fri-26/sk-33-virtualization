import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

// The logged-in user: { id, email, name, is_admin, quota, used, storage_requested, admin_alerts? }; null when logged out.
export const useAuth = defineStore('auth', () => {
  const user = ref(null)
  let loaded = null

  // Load the current user once (cookie session).
  const load = () => (loaded ??= refresh().catch(() => null))
  // Reload it, e.g. after an upload changed the storage used.
  async function refresh() {
    user.value = await api('/auth/me')
  }

  async function login(email, password) {
    user.value = await api('/auth/login', { method: 'POST', body: { email, password } })
  }
  async function logout() {
    await api('/auth/logout', { method: 'POST' })
    user.value = null
  }
  // A track the user may edit or delete: their own uploads, or any track for admins.
  const canEdit = (track) => !!user.value && (user.value.is_admin || track.uploaded_by === user.value.id)
  return { user, load, refresh, login, logout, canEdit }
})
