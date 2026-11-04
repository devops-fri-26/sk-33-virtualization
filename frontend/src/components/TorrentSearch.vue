<script setup>
import { LoaderCircle, Magnet } from 'lucide-vue-next'
import { ref } from 'vue'
import { api, fmtSize } from '../api'

const props = defineProps({ q: { type: String, required: true } })
const results = ref(null)
const busy = ref(false)
const error = ref('')
const started = ref(new Set())

async function search() {
  busy.value = true
  error.value = ''
  try {
    results.value = await api(`/torrents/search?q=${encodeURIComponent(props.q)}`)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
async function download(r) {
  error.value = ''
  try {
    await api('/torrents', { method: 'POST', body: { title: r.title, url: r.url } })
    started.value = new Set([...started.value, r.url])
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <section class="rounded-lg bg-white/5 p-5">
    <div class="flex flex-wrap items-center gap-4">
      <Magnet class="h-8 w-8 text-muted" />
      <div class="flex-1">
        <p class="font-bold">Not in your library?</p>
        <p class="text-sm text-muted">Search torrents and the server will download and import it.</p>
      </div>
      <button class="flex items-center gap-2 rounded-full border border-white/30 px-5 py-2 text-sm font-bold hover:scale-105 hover:border-white disabled:opacity-50" :disabled="busy" @click="search">
        <LoaderCircle v-if="busy" class="h-4 w-4 animate-spin" />
        {{ busy ? 'Searching…' : `Search torrents for “${q}”` }}
      </button>
    </div>
    <p v-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>
    <p v-if="results && !results.length" class="mt-4 text-sm text-muted">No torrents found.</p>
    <div v-if="results?.length" class="mt-4 divide-y divide-white/5">
      <div v-for="r in results" :key="r.url" class="flex items-center gap-4 py-3">
        <div class="min-w-0 flex-1">
          <p class="text-sm break-words">{{ r.title }}</p>
          <p class="text-xs text-muted">
            {{ fmtSize(r.size) }} · <span class="text-accent">{{ r.seeders }} seeders</span> · {{ r.leechers }} leechers<span v-if="r.indexer"> · {{ r.indexer }}</span>
          </p>
        </div>
        <RouterLink v-if="started.has(r.url)" to="/torrents" class="shrink-0 text-sm font-bold text-accent hover:underline">Downloading →</RouterLink>
        <button v-else class="shrink-0 rounded-full bg-white px-4 py-1.5 text-sm font-bold text-black hover:scale-105" @click="download(r)">Download</button>
      </div>
    </div>
  </section>
</template>
