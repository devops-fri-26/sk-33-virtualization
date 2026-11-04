import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

export const useAuth = defineStore('auth', () => {
  const user = ref(null)
  let loaded = null

  // Load the current user once (cookie session); null when logged out.
  const load = () => (loaded ??= api('/auth/me').then((u) => (user.value = u)).catch(() => null))

  async function login(email, password) {
    user.value = await api('/auth/login', { method: 'POST', body: { email, password } })
  }
  async function logout() {
    await api('/auth/logout', { method: 'POST' })
    user.value = null
  }
  return { user, load, login, logout }
})
