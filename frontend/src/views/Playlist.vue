<script setup>
import { Shuffle, Trash2 } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, coverUrl, fmtTotal } from '../api'
import MediaHeader from '../components/MediaHeader.vue'
import PlayButton from '../components/PlayButton.vue'
import TrackList from '../components/TrackList.vue'
import { useAuth } from '../stores/auth'
import { usePlayer } from '../stores/player'
import { usePlaylists } from '../stores/playlists'

const id = useRoute().params.id
const router = useRouter()
const auth = useAuth()
const player = usePlayer()
const playlists = usePlaylists()
const pl = ref(null)
const name = ref('')
const error = ref('')

const source = computed(() => ({ label: pl.value?.name, to: `/playlist/${id}` }))
const cover = computed(() => coverUrl(pl.value?.tracks.find((t) => t.album?.cover)?.album))
const total = computed(() => pl.value.tracks.reduce((s, t) => s + t.duration, 0))

async function run(fn) {
  error.value = ''
  try {
    await fn()
  } catch (e) {
    error.value = e.message
  }
}
run(async () => {
  pl.value = await api(`/playlists/${id}`)
  name.value = pl.value.name
})
const rename = () =>
  run(async () => {
    if (!name.value.trim()) name.value = pl.value.name
    if (name.value === pl.value.name) return
    pl.value.name = (await api(`/playlists/${id}`, { method: 'PATCH', body: { name: name.value } })).name
    playlists.load()
  })
const removeEntry = (t) =>
  run(async () => {
    pl.value = await api(`/playlists/${id}/tracks/${t.entry_id}`, { method: 'DELETE' })
    playlists.load()
  })
const move = (i, dir) =>
  run(async () => {
    const ids = pl.value.tracks.map((t) => t.entry_id)
    ;[ids[i], ids[i + dir]] = [ids[i + dir], ids[i]]
    pl.value = await api(`/playlists/${id}/order`, { method: 'PUT', body: { entry_ids: ids } })
  })
const destroy = () =>
  run(async () => {
    if (!confirm(`Delete playlist "${pl.value.name}"?`)) return
    await api(`/playlists/${id}`, { method: 'DELETE' })
    await playlists.load()
    router.push('/library')
  })
</script>

<template>
  <div v-if="pl" class="pb-10">
    <MediaHeader type="Playlist" :title="pl.name" :image="cover" icon="playlist">
      <template #title>
        <input
          v-model="name"
          title="Click to rename"
          class="my-2 w-full rounded-md bg-transparent text-4xl font-black tracking-tight outline-none hover:bg-white/10 focus:bg-white/10 md:text-7xl"
          @change="rename"
          @keyup.enter="$event.target.blur()"
        />
      </template>
      <template #meta>
        <span class="font-bold text-white">{{ auth.user?.email }}</span>
        <span>· {{ pl.tracks.length }} {{ pl.tracks.length === 1 ? 'song' : 'songs' }}<template v-if="pl.tracks.length">, {{ fmtTotal(total) }}</template></span>
      </template>
      <template #actions>
        <PlayButton v-if="pl.tracks.length" size="lg" :playing="player.isPlayingSource(source.to)" @click="player.playSource(pl.tracks, source)" />
        <button v-if="pl.tracks.length" :class="player.shuffle ? 'text-accent' : 'text-muted hover:text-white'" :title="player.shuffle ? 'Disable shuffle' : 'Enable shuffle'" @click="player.toggleShuffle">
          <Shuffle class="h-8 w-8" />
        </button>
        <button class="text-muted hover:text-white" title="Delete playlist" @click="destroy"><Trash2 class="h-7 w-7" /></button>
      </template>
    </MediaHeader>
    <p v-if="error" class="px-6 pb-4 text-sm text-red-400">{{ error }}</p>
    <TrackList v-if="pl.tracks.length" class="px-2 md:px-6" :tracks="pl.tracks" :source="source" playlist @move="move" @remove="removeEntry" />
    <div v-else class="px-6 py-10 text-center text-muted">
      <p class="text-lg font-bold text-white">This playlist is empty</p>
      <p class="mt-1">Add songs with the ⊕ button or the ⋯ menu on any song.</p>
      <RouterLink to="/search" class="mt-6 inline-block rounded-full bg-white px-6 py-3 font-bold text-black hover:scale-105">Find songs</RouterLink>
    </div>
  </div>
  <p v-else-if="error" class="px-6 pt-16 text-muted">{{ error }}</p>
</template>
