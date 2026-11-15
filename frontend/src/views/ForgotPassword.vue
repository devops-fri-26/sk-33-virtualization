<script setup>
import { MailCheck } from 'lucide-vue-next'
import { ref } from 'vue'
import { api } from '../api'
import AuthLayout, { button, input } from '../components/AuthLayout.vue'

const email = ref('')
const sent = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    sent.value = (await api('/auth/forgot-password', { method: 'POST', body: { email: email.value } })).detail
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthLayout :title="sent ? 'Check your email' : 'Reset your password'">
    <div v-if="sent" class="text-center text-muted">
      <MailCheck class="mx-auto mb-4 h-12 w-12 text-accent" />
      {{ sent }}
    </div>
    <form v-else class="space-y-4" @submit.prevent="submit">
      <p class="text-muted">Enter your email and we'll send you a link to set a new password.</p>
      <label class="block text-sm font-bold">Email<input v-model="email" type="email" required autocomplete="email" :class="input" class="mt-2 font-normal" /></label>
      <p v-if="error" class="rounded-md bg-red-500/15 px-3 py-2 text-sm text-red-300">{{ error }}</p>
      <button :class="button" :disabled="busy">Send link</button>
    </form>
    <p class="mt-8 border-t border-white/10 pt-6 text-center text-muted">
      <RouterLink to="/login" class="font-bold text-white underline hover:text-accent">Back to log in</RouterLink>
    </p>
  </AuthLayout>
</template>
