<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import AuthLayout, { button, input } from '../components/AuthLayout.vue'

const route = useRoute()
const password = ref('')
const repeat = ref('')
const done = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  if (password.value !== repeat.value) return (error.value = "The passwords don't match")
  busy.value = true
  try {
    const body = { token: route.query.token || '', password: password.value }
    done.value = (await api('/auth/reset-password', { method: 'POST', body })).detail
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthLayout :title="done ? 'Password changed' : 'Choose a new password'">
    <template v-if="done">
      <p class="mb-8 text-center text-accent">{{ done }}</p>
      <RouterLink to="/login" :class="button" class="block text-center">Log in</RouterLink>
    </template>
    <form v-else class="space-y-4" @submit.prevent="submit">
      <label class="block text-sm font-bold">
        New password
        <input v-model="password" type="password" required minlength="8" autocomplete="new-password" :class="input" class="mt-2 font-normal" />
        <span class="mt-1 block text-xs font-normal text-muted">At least 8 characters.</span>
      </label>
      <label class="block text-sm font-bold">Repeat it<input v-model="repeat" type="password" required autocomplete="new-password" :class="input" class="mt-2 font-normal" /></label>
      <p v-if="error" class="rounded-md bg-red-500/15 px-3 py-2 text-sm text-red-300">
        {{ error }}
        <RouterLink v-if="error.includes('link')" to="/forgot-password" class="mt-1 block font-bold text-white underline">Get a new link</RouterLink>
      </p>
      <button :class="button" :disabled="busy">Change password</button>
    </form>
  </AuthLayout>
</template>
