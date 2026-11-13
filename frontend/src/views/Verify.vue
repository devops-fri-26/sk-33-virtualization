<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import AuthLayout, { button } from '../components/AuthLayout.vue'

const route = useRoute()
const message = ref('Verifying your email…')
const ok = ref(false)
const approved = ref(false)

onMounted(async () => {
  try {
    const res = await api(`/auth/verify?token=${encodeURIComponent(route.query.token || '')}`, { method: 'POST' })
    message.value = res.detail
    approved.value = res.approved
    ok.value = true
  } catch (e) {
    message.value = e.message
  }
})
</script>

<template>
  <AuthLayout :title="approved ? 'You\'re all set' : ok ? 'Email verified' : 'Email verification'">
    <p class="mb-8 text-center" :class="ok ? 'text-accent' : 'text-muted'">{{ message }}</p>
    <RouterLink v-if="approved" to="/login" :class="button" class="block text-center">Log in</RouterLink>
    <RouterLink v-else to="/login" class="block text-center text-muted underline hover:text-white">Back to log in</RouterLink>
  </AuthLayout>
</template>
