<script setup>
import { HardDrive, KeyRound, Mail, MonitorSmartphone, UserRound } from 'lucide-vue-next'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import StoragePanel from '../components/StoragePanel.vue'
import { useAuth } from '../stores/auth'
import { usePlayer } from '../stores/player'

const auth = useAuth()
const player = usePlayer()
const router = useRouter()

const name = ref(auth.user.name ?? '')
const emailForm = reactive({ email: '', password: '' })
const pw = reactive({ current: '', new: '', repeat: '' })
const result = reactive({ name: null, email: null, password: null }) // per section: { ok, text }
const busy = ref('')

const card = 'rounded-lg bg-white/5 p-5'
const heading = 'mb-4 flex items-center gap-2 text-lg font-bold'
const label = 'block text-sm font-bold'
const field =
  'mt-2 w-full rounded-md bg-white/10 px-3 py-2.5 font-normal outline-none ring-1 ring-transparent placeholder:text-muted hover:ring-white/30 focus:ring-2 focus:ring-white'
const primary = 'rounded-full bg-white px-5 py-2 font-bold text-black transition hover:scale-105 disabled:opacity-50'

async function run(section, fn) {
  result[section] = null
  busy.value = section
  try {
    result[section] = { ok: true, text: await fn() }
  } catch (e) {
    result[section] = { ok: false, text: e.message }
  } finally {
    busy.value = ''
  }
}

const saveName = () =>
  run('name', async () => {
    auth.user = await api('/account', { method: 'PATCH', body: { name: name.value } })
    return 'Saved'
  })

const changeEmail = () =>
  run('email', async () => {
    const { detail } = await api('/account/email', { method: 'POST', body: { ...emailForm } })
    emailForm.email = emailForm.password = ''
    return detail
  })

const changePassword = () =>
  run('password', async () => {
    if (pw.new !== pw.repeat) throw new Error("The new passwords don't match")
    const { detail } = await api('/account/password', { method: 'POST', body: { current: pw.current, new: pw.new } })
    pw.current = pw.new = pw.repeat = ''
    return detail
  })

async function logoutEverywhere() {
  if (!confirm('Log out on all your devices, including this one?')) return
  await api('/account/logout-everywhere', { method: 'POST' })
  player.reset()
  auth.user = null
  router.push('/login')
}
</script>

<template>
  <div class="px-4 pt-16 pb-10 md:px-6">
    <h1 class="mb-6 text-3xl font-bold">Settings</h1>
    <div class="max-w-2xl space-y-4">
      <section :class="card">
        <h2 :class="heading"><UserRound class="h-5 w-5 text-muted" /> Profile</h2>
        <form class="flex flex-wrap items-end gap-3" @submit.prevent="saveName">
          <label :class="label" class="flex-1 basis-60">
            Display name
            <input v-model="name" maxlength="100" placeholder="Your name" autocomplete="name" :class="field" />
          </label>
          <button :class="primary" :disabled="busy === 'name'">Save</button>
        </form>
        <p class="mt-2 text-xs text-muted">Shown in your account menu and to admins.</p>
        <p v-if="result.name" class="mt-3 text-sm" :class="result.name.ok ? 'text-accent' : 'text-red-400'">{{ result.name.text }}</p>
      </section>

      <section :class="card">
        <h2 :class="heading"><Mail class="h-5 w-5 text-muted" /> Email</h2>
        <p class="mb-4 text-sm text-muted">
          Your email is <span class="text-white">{{ auth.user.email }}</span>. To change it, we send a link to the new address; your email changes
          when you open it.
        </p>
        <form class="grid gap-3 sm:grid-cols-2" @submit.prevent="changeEmail">
          <label :class="label">New email<input v-model="emailForm.email" type="email" required autocomplete="email" :class="field" /></label>
          <label :class="label">
            Current password<input v-model="emailForm.password" type="password" required autocomplete="current-password" :class="field" />
          </label>
          <div class="sm:col-span-2"><button :class="primary" :disabled="busy === 'email'">Send confirmation link</button></div>
        </form>
        <p v-if="result.email" class="mt-3 text-sm" :class="result.email.ok ? 'text-accent' : 'text-red-400'">{{ result.email.text }}</p>
      </section>

      <section :class="card">
        <h2 :class="heading"><KeyRound class="h-5 w-5 text-muted" /> Password</h2>
        <form class="grid gap-3 sm:grid-cols-2" @submit.prevent="changePassword">
          <label :class="label" class="sm:col-span-2">
            Current password<input v-model="pw.current" type="password" required autocomplete="current-password" :class="field" />
          </label>
          <label :class="label">
            New password<input v-model="pw.new" type="password" required minlength="8" autocomplete="new-password" :class="field" />
            <span class="mt-1 block text-xs font-normal text-muted">At least 8 characters.</span>
          </label>
          <label :class="label">Repeat new password<input v-model="pw.repeat" type="password" required autocomplete="new-password" :class="field" /></label>
          <div class="sm:col-span-2"><button :class="primary" :disabled="busy === 'password'">Change password</button></div>
        </form>
        <p v-if="result.password" class="mt-3 text-sm" :class="result.password.ok ? 'text-accent' : 'text-red-400'">{{ result.password.text }}</p>
      </section>

      <section :class="card">
        <h2 :class="heading"><HardDrive class="h-5 w-5 text-muted" /> Storage</h2>
        <p class="mb-4 text-sm text-muted">Music you upload counts against your space. Deleting your uploads frees it again.</p>
        <StoragePanel always-offer />
      </section>

      <section :class="card">
        <h2 :class="heading"><MonitorSmartphone class="h-5 w-5 text-muted" /> Devices</h2>
        <p class="mb-4 text-sm text-muted">Lost a phone or logged in on someone else's computer? This logs you out everywhere.</p>
        <button class="rounded-full border border-white/30 px-5 py-2 font-bold transition hover:border-white" @click="logoutEverywhere">
          Log out on all devices
        </button>
      </section>
    </div>
  </div>
</template>
