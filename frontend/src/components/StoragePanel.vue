<script setup>
import { Clock3 } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { api, fmtBytes } from '../api'
import { useAuth } from '../stores/auth'

// The logged-in user's upload space, with "ask for more space" (always, or only when nearly full).
const props = defineProps({ alwaysOffer: Boolean })
const auth = useAuth()
const u = computed(() => auth.user)
const pct = computed(() => (u.value.quota ? Math.min(100, (u.value.used / u.value.quota) * 100) : 0))
const full = computed(() => u.value.quota !== null && u.value.used >= u.value.quota)
const offer = computed(() => u.value.quota !== null && (props.alwaysOffer || pct.value >= 90))
const error = ref('')

async function request() {
  error.value = ''
  try {
    auth.user = await api('/account/storage-request', { method: 'POST' })
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <div>
    <p class="text-sm">
      <span class="font-bold">{{ fmtBytes(u.used) }}</span>
      <span class="text-muted">{{ u.quota === null ? ' used · no limit' : ` of ${fmtBytes(u.quota)} used` }}</span>
    </p>
    <div v-if="u.quota !== null" class="mt-2 h-2 overflow-hidden rounded-full bg-white/15">
      <div class="h-full rounded-full" :class="full ? 'bg-red-500' : pct >= 90 ? 'bg-amber-400' : 'bg-accent'" :style="{ width: `${pct}%` }" />
    </div>
    <p v-if="full" class="mt-3 text-sm text-red-300">Your storage is full. Ask an admin for more space to upload more music.</p>
    <template v-if="offer">
      <p v-if="u.storage_requested" class="mt-3 flex items-center gap-2 text-sm text-muted">
        <Clock3 class="h-4 w-4 shrink-0" /> You asked for more space. An admin will look at it.
      </p>
      <button v-else class="mt-3 rounded-full border border-white/30 px-4 py-1.5 text-sm font-bold hover:border-white" @click="request">
        Ask for more space
      </button>
    </template>
    <p v-if="error" class="mt-2 text-sm text-red-400">{{ error }}</p>
  </div>
</template>
