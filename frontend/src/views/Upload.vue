<script setup>
import { CloudUpload, LoaderCircle } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { api } from '../api'
import StoragePanel from '../components/StoragePanel.vue'
import TrackList from '../components/TrackList.vue'
import { useAuth } from '../stores/auth'

const AUDIO = ['flac', 'wav', 'm4a', 'mp3', 'ogg', 'opus']
// Sent along with the songs of their folder: album covers and missing tags (archive.org XML, Kodi/Jellyfin .nfo).
const EXTRAS = ['jpg', 'jpeg', 'png', 'webp', 'xml', 'nfo']
const MAX_EXTRA = 20 * 1024 ** 2 // the server ignores bigger ones (booklet scans)
const BATCH = 500 * 1024 ** 2 // songs per request; nginx takes up to 2 GB
const MAX_FILES = 400 // files per request (the server stops reading a request after 2000)
const MAX_FILE = 2 * 1024 ** 3 - 32 * 1024 ** 2 // one song, with room for the rest of the request
const ART_DIR_COVER = /cover|front|folder/i // pictures in a subfolder (Album/Artwork/Front.jpg) worth sending

const auth = useAuth()
const full = computed(() => auth.user.quota !== null && auth.user.used >= auth.user.quota)
const busy = ref(false)
const progress = ref(null) // { done, total, folder }
const imported = ref([])
const errors = ref([])
const skipped = ref('') // e.g. ".cue, .log (3)"

const ext = (path) => (path.includes('.') ? path.split('.').pop().toLowerCase() : '')
const dirOf = (path) => path.split('/').slice(0, -1).join('/')
const name = (path) => path.split('/').pop()

/** Requests to send: per folder its songs (split into BATCH-sized parts) plus the extras of that folder,
 * the folders above it and its direct subfolders (covers only). */
function plan(files) {
  const songs = new Map() // folder -> [{ file, path }]
  const extras = []
  const other = {}
  const tooBig = []
  for (const file of files) {
    const path = file.webkitRelativePath || file.name
    if (name(path).startsWith('.')) continue // .DS_Store and other hidden files
    const e = ext(path)
    if (AUDIO.includes(e) && file.size > MAX_FILE) tooBig.push(path)
    else if (AUDIO.includes(e)) songs.set(dirOf(path), [...(songs.get(dirOf(path)) ?? []), { file, path }])
    else if (EXTRAS.includes(e) && file.size <= MAX_EXTRA) extras.push({ file, path })
    else other[e ? `.${e}` : name(path)] = (other[e ? `.${e}` : name(path)] ?? 0) + 1
  }
  const batches = []
  for (const [dir, list] of [...songs].sort(([a], [b]) => a.localeCompare(b))) {
    const near = extras
      .filter(({ path }) => {
        const d = dirOf(path)
        const above = d === '' || dir === d || dir.startsWith(`${d}/`)
        return above || (dirOf(d) === dir && d !== dir && ART_DIR_COVER.test(name(path)))
      })
      .slice(0, MAX_FILES)
    let part = []
    let size = 0
    for (const item of list.sort((a, b) => a.path.localeCompare(b.path))) {
      if (part.length && (size + item.file.size > BATCH || part.length >= MAX_FILES)) {
        batches.push({ dir, files: [...part, ...near] })
        part = []
        size = 0
      }
      part.push(item)
      size += item.file.size
    }
    batches.push({ dir, files: [...part, ...near] })
  }
  const skippedText = Object.entries(other)
    .map(([k, n]) => (n > 1 ? `${k} (${n})` : k))
    .join(', ')
  return { batches, skippedText, tooBig }
}

async function upload(e) {
  const { batches, skippedText, tooBig } = plan([...e.target.files])
  e.target.value = ''
  errors.value = tooBig.map((file) => ({ file, error: 'Bigger than 2 GB, which is the most one upload can take' }))
  skipped.value = skippedText
  if (!batches.length) {
    if (!skippedText && !tooBig.length) errors.value = [{ file: 'Upload', error: 'No files found' }]
    return
  }
  busy.value = true
  try {
    for (const [i, b] of batches.entries()) {
      progress.value = { done: i, total: batches.length, folder: name(b.dir) }
      const form = new FormData()
      for (const { file, path } of b.files) {
        form.append('files', file)
        form.append('paths', path)
      }
      try {
        const res = await api('/upload', { method: 'POST', form })
        imported.value = [...res.imported, ...imported.value]
        errors.value.push(...res.errors)
      } catch (err) {
        errors.value.push({ file: b.dir || 'Upload', error: err.message })
      }
      await auth.refresh().catch(() => {}) // storage used
      if (full.value && i < batches.length - 1) {
        errors.value.push({ file: 'Upload', error: `Storage is full: ${batches.length - i - 1} more folder part(s) not uploaded` })
        break
      }
    }
  } finally {
    busy.value = false
    progress.value = null
  }
}
</script>

<template>
  <div class="px-4 pt-16 pb-10 md:px-6">
    <h1 class="mb-6 text-3xl font-bold">Upload music</h1>
    <StoragePanel class="mb-6 max-w-md" />
    <div
      class="flex flex-col items-center rounded-xl border-2 border-dashed border-white/20 px-6 py-14 text-center"
      :class="{ 'opacity-60': busy || full }"
    >
      <LoaderCircle v-if="busy" class="mb-4 h-12 w-12 animate-spin text-accent" />
      <CloudUpload v-else class="mb-4 h-12 w-12 text-muted" />
      <span class="text-lg font-bold">
        <template v-if="!busy">Upload songs or a whole folder</template>
        <template v-else-if="progress?.total > 1">Uploading {{ progress.done + 1 }} of {{ progress.total }}: {{ progress.folder || 'files' }}…</template>
        <template v-else>Uploading…</template>
      </span>
      <span class="mt-1 max-w-lg text-sm text-muted">
        FLAC, WAV, M4A/ALAC, MP3, OGG, Opus. Files are kept exactly as uploaded. A folder's cover picture and
        XML/NFO metadata are used for album art and missing tags.
      </span>
      <div v-if="!busy" class="mt-6 flex flex-wrap justify-center gap-3">
        <label class="cursor-pointer rounded-full bg-white px-6 py-2.5 font-bold text-black hover:scale-105" :class="{ 'pointer-events-none': full }">
          Browse files
          <input type="file" multiple :accept="[...AUDIO, ...EXTRAS].map((e) => `.${e}`).join(',')" class="hidden" :disabled="full" @change="upload" />
        </label>
        <label class="cursor-pointer rounded-full px-6 py-2.5 font-bold ring-1 ring-white/40 hover:ring-white" :class="{ 'pointer-events-none': full }">
          Browse folder
          <input type="file" webkitdirectory class="hidden" :disabled="full" @change="upload" />
        </label>
      </div>
    </div>

    <p v-if="skipped" class="mt-6 text-sm text-muted">Not uploaded (not a supported audio format): {{ skipped }}</p>

    <div v-if="errors.length" class="mt-6 rounded-lg bg-red-500/10 p-4 text-sm ring-1 ring-red-500/30">
      <p class="mb-1 font-bold text-red-300">Some files were not imported</p>
      <p v-for="(e, i) in errors" :key="i" class="text-red-200/80">{{ e.file }}: {{ e.error }}</p>
    </div>

    <section v-if="imported.length" class="mt-8">
      <h2 class="mb-2 text-2xl font-bold">Imported</h2>
      <TrackList :tracks="imported" :source="{ label: 'Uploads', to: '/upload' }" />
    </section>
  </div>
</template>
