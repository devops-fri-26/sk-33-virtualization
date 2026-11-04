<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import AuthLayout, { button } from '../components/AuthLayout.vue'

const route = useRoute()
const message = ref('Verifying your email…')
const ok = ref(false)

onMounted(async () => {
  try {
    message.value = (await api(`/auth/verify?token=${encodeURIComponent(route.query.token || '')}`, { method: 'POST' })).detail
    ok.value = true
  } catch (e) {
    message.value = e.message
  }
})
</script>

<template>
  <AuthLayout :title="ok ? 'You\'re all set' : 'Email verification'">
    <p class="mb-8 text-center" :class="ok ? 'text-accent' : 'text-muted'">{{ message }}</p>
    <RouterLink v-if="ok" to="/login" :class="button" class="block text-center">Log in</RouterLink>
  </AuthLayout>
</template>
