<script setup>
import { CloudUpload, LoaderCircle } from 'lucide-vue-next'
import { ref } from 'vue'
import { api } from '../api'
import TrackList from '../components/TrackList.vue'

const busy = ref(false)
const imported = ref([])
const errors = ref([])

async function upload(e) {
  const files = [...e.target.files]
  if (!files.length) return
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  busy.value = true
  try {
    const res = await api('/upload', { method: 'POST', form })
    imported.value = [...res.imported, ...imported.value]
    errors.value = res.errors
  } catch (err) {
    errors.value = [{ file: 'Upload', error: err.message }]
  } finally {
    busy.value = false
    e.target.value = ''
  }
}
</script>

<template>
  <div class="px-4 pt-16 pb-10 md:px-6">
    <h1 class="mb-6 text-3xl font-bold">Upload music</h1>
    <label
      class="flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed border-white/20 px-6 py-14 text-center transition-colors hover:border-white/50 hover:bg-white/5"
      :class="{ 'pointer-events-none opacity-60': busy }"
    >
      <LoaderCircle v-if="busy" class="mb-4 h-12 w-12 animate-spin text-accent" />
      <CloudUpload v-else class="mb-4 h-12 w-12 text-muted" />
      <span class="text-lg font-bold">{{ busy ? 'Uploading…' : 'Choose files to upload' }}</span>
      <span class="mt-1 text-sm text-muted">FLAC, WAV, M4A/ALAC, MP3, OGG, Opus. Files are kept exactly as uploaded.</span>
      <span v-if="!busy" class="mt-6 rounded-full bg-white px-6 py-2.5 font-bold text-black">Browse files</span>
      <input type="file" multiple accept=".flac,.wav,.m4a,.mp3,.ogg,.opus" class="hidden" :disabled="busy" @change="upload" />
    </label>

    <div v-if="errors.length" class="mt-6 rounded-lg bg-red-500/10 p-4 text-sm ring-1 ring-red-500/30">
      <p class="mb-1 font-bold text-red-300">Some files were not imported</p>
      <p v-for="e in errors" :key="e.file" class="text-red-200/80">{{ e.file }}: {{ e.error }}</p>
    </div>

    <section v-if="imported.length" class="mt-8">
      <h2 class="mb-2 text-2xl font-bold">Imported</h2>
      <TrackList :tracks="imported" :source="{ label: 'Uploads', to: '/upload' }" />
    </section>
  </div>
</template>
