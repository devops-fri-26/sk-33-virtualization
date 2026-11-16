<script setup>
import { MailCheck } from 'lucide-vue-next'
import { ref } from 'vue'
import { api } from '../api'
import AuthLayout, { button, input } from '../components/AuthLayout.vue'

const email = ref('')
const password = ref('')
const repeat = ref('')
const sent = ref(false)
const error = ref('')
const busy = ref(false)
const resent = ref(false)

async function resend() {
  await api('/auth/resend-verification', { method: 'POST', body: { email: email.value } }).catch(() => {})
  resent.value = true
}

async function submit() {
  error.value = ''
  if (password.value !== repeat.value) return (error.value = "The passwords don't match")
  busy.value = true
  try {
    await api('/auth/register', { method: 'POST', body: { email: email.value, password: password.value } })
    sent.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthLayout :title="sent ? 'Check your email' : 'Sign up for Varsis'">
    <div v-if="sent" class="text-center text-muted">
      <MailCheck class="mx-auto mb-4 h-12 w-12 text-accent" />
      We sent a verification link to <span class="font-bold text-white">{{ email }}</span>. Open it to confirm your email.
      After that, an admin has to approve your account. We'll email you when they do.
      <p class="mt-6 text-sm">
        <span v-if="resent">Sent again.</span>
        <template v-else>Didn't get it? <button class="font-bold text-white underline" @click="resend">Send it again</button></template>
      </p>
    </div>
    <form v-else class="space-y-4" @submit.prevent="submit">
      <label class="block text-sm font-bold">Email<input v-model="email" type="email" required autocomplete="email" :class="input" class="mt-2 font-normal" /></label>
      <label class="block text-sm font-bold">
        Password
        <input v-model="password" type="password" required minlength="8" autocomplete="new-password" :class="input" class="mt-2 font-normal" />
        <span class="mt-1 block text-xs font-normal text-muted">At least 8 characters.</span>
      </label>
      <label class="block text-sm font-bold">Repeat password<input v-model="repeat" type="password" required autocomplete="new-password" :class="input" class="mt-2 font-normal" /></label>
      <p v-if="error" class="rounded-md bg-red-500/15 px-3 py-2 text-sm text-red-300">{{ error }}</p>
      <button :class="button" :disabled="busy">Sign up</button>
    </form>
    <p class="mt-8 border-t border-white/10 pt-6 text-center text-muted">
      Already have an account? <RouterLink to="/login" class="font-bold text-white underline hover:text-accent">Log in</RouterLink>
    </p>
  </AuthLayout>
</template>
