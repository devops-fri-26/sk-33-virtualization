<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import AuthLayout, { button, input } from '../components/AuthLayout.vue'
import { useAuth } from '../stores/auth'

const auth = useAuth()
const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)
const notice = ref('')

async function resend() {
  try {
    notice.value = (await api('/auth/resend-verification', { method: 'POST', body: { email: email.value } })).detail
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}

async function submit() {
  error.value = notice.value = ''
  busy.value = true
  try {
    await auth.login(email.value, password.value)
    router.push('/')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthLayout title="Log in to Varsis">
    <form class="space-y-4" @submit.prevent="submit">
      <label class="block text-sm font-bold">Email<input v-model="email" type="email" required autocomplete="email" :class="input" class="mt-2 font-normal" /></label>
      <label class="block text-sm font-bold">Password<input v-model="password" type="password" required autocomplete="current-password" :class="input" class="mt-2 font-normal" /></label>
      <p v-if="error" class="rounded-md bg-red-500/15 px-3 py-2 text-sm text-red-300">
        {{ error }}
        <button v-if="error === 'Email not verified'" type="button" class="mt-1 block font-bold text-white underline" @click="resend">
          Send the verification email again
        </button>
      </p>
      <p v-if="notice" class="rounded-md bg-accent/15 px-3 py-2 text-sm text-accent">{{ notice }}</p>
      <button :class="button" :disabled="busy">Log in</button>
      <RouterLink to="/forgot-password" class="block text-center text-sm text-muted underline hover:text-white">Forgot your password?</RouterLink>
    </form>
    <p class="mt-8 border-t border-white/10 pt-6 text-center text-muted">
      Don't have an account? <RouterLink to="/register" class="font-bold text-white underline hover:text-accent">Sign up</RouterLink>
    </p>
  </AuthLayout>
</template>
