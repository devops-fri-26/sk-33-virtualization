<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import AuthLayout, { button } from '../components/AuthLayout.vue'
import { useAuth } from '../stores/auth'

// Opened from the link sent when changing the email in Settings (works logged in or not).
const route = useRoute()
const auth = useAuth()
const message = ref('Confirming your new email…')
const ok = ref(false)

onMounted(async () => {
  try {
    message.value = (await api(`/auth/confirm-email?token=${encodeURIComponent(route.query.token || '')}`, { method: 'POST' })).detail
    ok.value = true
    if (auth.user) auth.refresh().catch(() => {})
  } catch (e) {
    message.value = e.message
  }
})
</script>

<template>
  <AuthLayout :title="ok ? 'Email changed' : 'Confirm your email'">
    <p class="mb-8 text-center" :class="ok ? 'text-accent' : 'text-muted'">{{ message }}</p>
    <RouterLink :to="auth.user ? '/settings' : '/login'" :class="button" class="block text-center">
      {{ auth.user ? 'Back to settings' : 'Log in' }}
    </RouterLink>
  </AuthLayout>
</template>
