<script setup>
import { X } from 'lucide-vue-next'
import { ref } from 'vue'
import { api } from '../api'

// Edit a track's title, artists and album. Only the library entry changes, not the audio file.
const props = defineProps({ track: { type: Object, required: true } })
const emit = defineEmits(['close', 'saved'])
const title = ref(props.track.title)
const names = ref(props.track.artists.map((a) => a.name))
const input = ref('')
const album = ref(props.track.album?.title ?? '')
const albumArtist = ref(props.track.album?.artist?.name ?? '')
const suggestions = ref({ artists: [], albums: [] })
const error = ref('')
const busy = ref(false)

const field = 'w-full rounded-md bg-white/10 px-3 py-2 font-normal outline-none placeholder:text-muted focus:ring-2 focus:ring-white'
const label = 'block text-sm font-bold'

async function suggest(text) {
  const q = text.trim()
  if (!q) return
  const r = await api(`/search?q=${encodeURIComponent(q)}`).catch(() => null)
  if (r) suggestions.value = { artists: r.artists, albums: r.albums }
}
// Picking an album that exists also fills in its album artist.
function albumTyped() {
  suggest(album.value)
  const match = suggestions.value.albums.find((a) => a.title === album.value.trim())
  if (match) albumArtist.value = match.artist?.name ?? ''
}
function add() {
  const n = input.value.trim()
  if (n && !names.value.includes(n)) names.value.push(n)
  input.value = ''
}
async function save() {
  add()
  error.value = ''
  if (!title.value.trim()) return (error.value = "The title can't be empty")
  const body = { title: title.value, album: album.value }
  // A track that had no album gets its first artist as album artist unless one is typed in.
  if (album.value.trim() && (albumArtist.value.trim() || props.track.album)) body.album_artist = albumArtist.value
  if (names.value.length) body.artists = names.value
  busy.value = true
  try {
    emit('saved', await api(`/tracks/${props.track.id}`, { method: 'PATCH', body }))
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @click.self="emit('close')">
      <div class="max-h-full w-full max-w-md overflow-y-auto rounded-xl bg-highlight p-6 shadow-2xl">
        <div class="mb-5 flex items-center justify-between">
          <h2 class="text-2xl font-bold">Edit details</h2>
          <button class="rounded-full p-1 text-muted hover:bg-white/10 hover:text-white" title="Close" @click="emit('close')"><X class="h-5 w-5" /></button>
        </div>

        <label :class="label">Title<input v-model="title" maxlength="500" :class="field" class="mt-2" /></label>

        <p :class="label" class="mt-4 mb-2">Artists</p>
        <div class="mb-2 flex min-h-8 flex-wrap gap-2">
          <span v-for="(n, i) in names" :key="n" class="flex items-center gap-1 rounded-full bg-white/10 py-1 pr-1.5 pl-3 text-sm">
            {{ n }}
            <button class="rounded-full p-0.5 text-muted hover:bg-white/10 hover:text-white" :title="`Remove ${n}`" @click="names.splice(i, 1)"><X class="h-3.5 w-3.5" /></button>
          </span>
          <span v-if="!names.length" class="text-sm text-muted">No artists yet.</span>
        </div>
        <form class="flex gap-2" @submit.prevent="add">
          <input v-model="input" list="editor-artists" placeholder="Artist name" maxlength="200" :class="field" class="flex-1" @input="suggest(input)" />
          <button class="rounded-full border border-white/30 px-4 text-sm font-bold hover:border-white">Add</button>
        </form>

        <label :class="label" class="mt-4">
          Album
          <input v-model="album" list="editor-albums" placeholder="No album" maxlength="500" :class="field" class="mt-2" @input="albumTyped" />
        </label>
        <label v-if="album.trim()" :class="label" class="mt-4">
          Album artist
          <input v-model="albumArtist" list="editor-artists" :placeholder="track.album ? 'None' : (names[0] ?? 'None')" maxlength="200" :class="field" class="mt-2" @input="suggest(albumArtist)" />
          <span class="mt-1 block text-xs font-normal text-muted">
            Tracks with the same album title and album artist are one album. Use “Various Artists” for a compilation.
          </span>
        </label>
        <datalist id="editor-artists">
          <option v-for="a in suggestions.artists" :key="a.id" :value="a.name" />
        </datalist>
        <datalist id="editor-albums">
          <option v-for="a in suggestions.albums" :key="a.id" :value="a.title">{{ a.artist?.name }}</option>
        </datalist>

        <p v-if="error" class="mt-3 text-sm text-red-400">{{ error }}</p>
        <div class="mt-6 flex justify-end gap-3">
          <button class="px-4 py-2 font-bold text-muted hover:text-white" @click="emit('close')">Cancel</button>
          <button class="rounded-full bg-white px-6 py-2 font-bold text-black hover:scale-105 disabled:opacity-50" :disabled="busy" @click="save">Save</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
