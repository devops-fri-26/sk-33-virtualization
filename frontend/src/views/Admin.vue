<script setup>
import { Ban, Check, Clock3, Shield, Trash2, UserCheck, X } from 'lucide-vue-next'
import { computed, onMounted, reactive, ref } from 'vue'
import { api, fmtBytes, GB } from '../api'
import { useAuth } from '../stores/auth'
import { useUi } from '../stores/ui'

const auth = useAuth()
const ui = useUi()
const users = ref(null)
const error = ref('')
const drafts = reactive({}) // user id -> { gb, unlimited }: the storage limit form

const pending = computed(() => (users.value ?? []).filter((u) => !u.is_approved && !u.is_disabled))
// Storage requests first, then newest.
const members = computed(() =>
  (users.value ?? []).filter((u) => u.is_approved || u.is_disabled).sort((a, b) => b.storage_requested - a.storage_requested),
)

const primary = 'flex items-center gap-1.5 rounded-full bg-white px-4 py-1.5 text-sm font-bold text-black transition hover:scale-105'
const secondary = 'flex items-center gap-1.5 rounded-full border border-white/30 px-4 py-1.5 text-sm font-bold transition hover:border-white'
const badge = 'rounded-full px-2 text-xs leading-5 font-bold'

const label = (u) => u.name || u.email
const date = (s) => new Date(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const pct = (u) => (u.quota ? Math.min(100, (u.used / u.quota) * 100) : 0)
const resetDraft = (u) => (drafts[u.id] = { gb: u.quota === null ? '' : +(u.quota / GB).toFixed(1), unlimited: u.quota === null })

async function load() {
  users.value = await api('/admin/users')
  users.value.forEach(resetDraft)
}
onMounted(() => load().catch((e) => (error.value = e.message)))

async function patch(u, body, message) {
  try {
    const updated = await api(`/admin/users/${u.id}`, { method: 'PATCH', body })
    users.value.splice(users.value.findIndex((x) => x.id === u.id), 1, updated)
    resetDraft(updated)
    ui.notify(message)
    auth.refresh().catch(() => {}) // admin badge
  } catch (e) {
    ui.notify(e.message)
  }
}

const approve = (u) => patch(u, { is_approved: true }, `${label(u)} can now log in`)
const setAdmin = (u, on) => patch(u, { is_admin: on }, on ? `${label(u)} is now an admin` : `${label(u)} is no longer an admin`)
function setDisabled(u, on) {
  if (on && !confirm(`Disable ${label(u)}? They're logged out and can't log in until you enable them again.`)) return
  patch(u, { is_disabled: on }, on ? `${label(u)} is disabled` : `${label(u)} can log in again`)
}
function saveQuota(u) {
  const d = drafts[u.id]
  patch(u, { quota: d.unlimited ? null : Math.round(d.gb * GB) }, `Saved the storage limit of ${label(u)}`)
}

async function remove(u, reject = false) {
  const question = reject
    ? `Reject ${u.email}? Their account is deleted.`
    : `Delete the account of ${label(u)}? Their playlists are deleted. Music they uploaded stays in the library.`
  if (!confirm(question)) return
  try {
    await api(`/admin/users/${u.id}`, { method: 'DELETE' })
    users.value = users.value.filter((x) => x.id !== u.id)
    ui.notify(reject ? `Rejected ${u.email}` : `Deleted ${label(u)}`)
    auth.refresh().catch(() => {})
  } catch (e) {
    ui.notify(e.message)
  }
}
</script>

<template>
  <div class="px-4 pt-16 pb-10 md:px-6">
    <h1 class="mb-1 text-3xl font-bold">Admin</h1>
    <p class="mb-8 text-muted">Approve new accounts and manage who can use Varsis.</p>
    <p v-if="error" class="rounded-md bg-red-500/15 px-3 py-2 text-sm text-red-300">{{ error }}</p>
    <p v-else-if="!users" class="text-muted">Loading…</p>

    <template v-if="users">
      <section class="mb-10">
        <h2 class="mb-3 text-2xl font-bold">Waiting for approval <span class="text-muted">{{ pending.length }}</span></h2>
        <p v-if="!pending.length" class="text-muted">No one is waiting.</p>
        <div v-for="u in pending" :key="u.id" class="mb-2 flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg bg-white/5 p-4">
          <div class="min-w-0 flex-1 basis-60">
            <p class="truncate font-bold">{{ label(u) }}</p>
            <p class="truncate text-sm text-muted"><template v-if="u.name">{{ u.email }} · </template>Signed up {{ date(u.created_at) }}</p>
            <p v-if="!u.is_verified" class="mt-1 flex items-center gap-1.5 text-sm text-amber-300">
              <Clock3 class="h-4 w-4 shrink-0" /> Hasn't confirmed their email yet
            </p>
          </div>
          <div class="flex gap-2">
            <button :class="primary" @click="approve(u)"><Check class="h-4 w-4" /> Approve</button>
            <button :class="secondary" @click="remove(u, true)"><X class="h-4 w-4" /> Reject</button>
          </div>
        </div>
      </section>

      <section>
        <h2 class="mb-3 text-2xl font-bold">Users <span class="text-muted">{{ members.length }}</span></h2>
        <div v-for="u in members" :key="u.id" class="mb-2 rounded-lg bg-white/5 p-4" :class="{ 'ring-1 ring-amber-400/60': u.storage_requested }">
          <div class="flex flex-wrap items-center gap-2">
            <span class="truncate font-bold">{{ label(u) }}</span>
            <span v-if="u.name" class="truncate text-sm text-muted">{{ u.email }}</span>
            <span v-if="u.id === auth.user.id" :class="badge" class="bg-white/15">You</span>
            <span v-if="u.is_admin" :class="badge" class="bg-accent/20 text-accent">Admin</span>
            <span v-if="u.is_disabled" :class="badge" class="bg-red-500/20 text-red-300">Disabled</span>
            <span v-if="u.storage_requested" :class="badge" class="bg-amber-400/20 text-amber-300">Asks for more space</span>
          </div>
          <p class="mt-1 text-sm text-muted">Joined {{ date(u.created_at) }} · {{ u.tracks }} {{ u.tracks === 1 ? 'track' : 'tracks' }} uploaded</p>

          <div class="mt-4 flex flex-wrap items-end gap-x-8 gap-y-4">
            <div class="min-w-48 flex-1">
              <p class="text-sm">
                <span class="font-bold">{{ fmtBytes(u.used) }}</span>
                <span class="text-muted">{{ u.quota === null ? ' used · no limit' : ` of ${fmtBytes(u.quota)} used` }}</span>
              </p>
              <div v-if="u.quota !== null" class="mt-2 h-2 overflow-hidden rounded-full bg-white/15">
                <div class="h-full rounded-full" :class="pct(u) >= 100 ? 'bg-red-500' : pct(u) >= 90 ? 'bg-amber-400' : 'bg-accent'" :style="{ width: `${pct(u)}%` }" />
              </div>
            </div>
            <form class="flex flex-wrap items-center gap-2 text-sm" @submit.prevent="saveQuota(u)">
              <span class="font-bold">Storage limit</span>
              <input
                v-model.number="drafts[u.id].gb"
                type="number"
                min="0"
                step="any"
                required
                :disabled="drafts[u.id].unlimited"
                class="w-20 rounded-md bg-white/10 px-2 py-1.5 outline-none focus:ring-2 focus:ring-white disabled:opacity-40"
                aria-label="Storage limit in GB"
              />
              GB
              <label class="flex items-center gap-1.5"><input v-model="drafts[u.id].unlimited" type="checkbox" class="accent-accent" /> No limit</label>
              <button :class="secondary">Save</button>
            </form>
          </div>

          <div v-if="u.id !== auth.user.id" class="mt-4 flex flex-wrap gap-2 border-t border-white/10 pt-4">
            <button :class="secondary" @click="setAdmin(u, !u.is_admin)"><Shield class="h-4 w-4" /> {{ u.is_admin ? 'Remove admin' : 'Make admin' }}</button>
            <button :class="secondary" @click="setDisabled(u, !u.is_disabled)">
              <component :is="u.is_disabled ? UserCheck : Ban" class="h-4 w-4" /> {{ u.is_disabled ? 'Enable' : 'Disable' }}
            </button>
            <button :class="secondary" class="text-red-300" @click="remove(u)"><Trash2 class="h-4 w-4" /> Delete account</button>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
