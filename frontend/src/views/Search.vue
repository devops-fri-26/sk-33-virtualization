<script setup>
import { Search as SearchIcon, X } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, coverUrl } from '../api'
import Card from '../components/Card.vue'
import Cover from '../components/Cover.vue'
import PlayButton from '../components/PlayButton.vue'
import TorrentSearch from '../components/TorrentSearch.vue'
import TrackList from '../components/TrackList.vue'
import { usePlayer } from '../stores/player'
import { useTorrents } from '../stores/torrents'

const torrents = useTorrents()
const route = useRoute()
const router = useRouter()
const player = usePlayer()
const q = ref(route.query.q ?? '')
const query = computed(() => q.value.trim())
const results = ref(null)
let timer
let seq = 0

async function search() {
  router.replace({ query: query.value ? { q: query.value } : {} })
  if (!query.value) return (results.value = null)
  const n = ++seq
  const r = await api(`/search?q=${encodeURIComponent(query.value)}`)
  if (n === seq) results.value = r // ignore responses to older keystrokes
}
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(search, 250)
})
// Back/forward between searches changes only the URL query; keep the input in sync.
watch(() => route.query.q, (v) => (v ?? '') !== query.value && (q.value = v ?? ''))
if (query.value) search()

const source = computed(() => ({ label: `“${query.value}”`, to: `/search?q=${encodeURIComponent(query.value)}` }))
const names = (t) => t.artists.map((a) => a.name).join(', ')

// Best single match: the first artist/album/song whose name contains the query, else the first result.
const top = computed(() => {
  const r = results.value
  if (!r) return null
  const [artist, album, track] = [r.artists[0], r.albums[0], r.tracks[0]]
  const candidates = [
    artist && { kind: 'artist', id: artist.id, title: artist.name, label: 'Artist', to: `/artist/${artist.id}`, round: true },
    album && { kind: 'album', id: album.id, title: album.title, label: `Album · ${album.artist?.name ?? ''}`, image: coverUrl(album), to: `/album/${album.id}` },
    track && { kind: 'track', title: track.title, label: `Song · ${names(track)}`, image: coverUrl(track.album), to: track.album ? `/album/${track.album.id}` : '/search' },
  ].filter(Boolean)
  return candidates.find((c) => c.title.toLowerCase().includes(query.value.toLowerCase())) ?? candidates[0] ?? null
})
const topPlaying = computed(() =>
  top.value?.kind === 'track' ? player.playing && player.current?.id === results.value.tracks[0].id : player.isPlayingSource(top.value?.to),
)
function playTop() {
  if (top.value.kind !== 'track') return player.playCollection(top.value.kind, top.value.id)
  if (player.current?.id === results.value.tracks[0].id) return player.toggle()
  player.playQueue(results.value.tracks, 0, source.value)
}
const empty = computed(() => results.value && !results.value.tracks.length && !results.value.albums.length && !results.value.artists.length)
</script>

<template>
  <div class="px-4 pb-10 md:px-6">
    <div class="sticky top-0 z-20 -mx-4 bg-surface px-4 py-3 md:-mx-6 md:px-6">
      <label class="flex w-full max-w-md items-center gap-3 rounded-full bg-white/10 px-4 py-3 ring-white transition focus-within:bg-white/15 focus-within:ring-2 hover:bg-white/15">
        <SearchIcon class="h-5 w-5 shrink-0 text-muted" />
        <input v-model="q" autofocus placeholder="Search songs, albums and artists" class="min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted" />
        <button v-if="q" class="text-muted hover:text-white" title="Clear" @click="q = ''"><X class="h-5 w-5" /></button>
      </label>
    </div>

    <div v-if="!query" class="mt-20 flex flex-col items-center text-center">
      <SearchIcon class="mb-4 h-14 w-14 text-muted" />
      <h2 class="text-2xl font-bold">Search your library</h2>
      <p class="mt-2 text-muted">Find songs, albums and artists.<template v-if="torrents.available"> Not there? Search torrents right from the results.</template></p>
    </div>

    <template v-else-if="results">
      <div v-if="empty" class="mt-12 mb-10 text-center">
        <h2 class="text-2xl font-bold">No results found for “{{ query }}”</h2>
        <p class="mt-2 text-muted">Check the spelling{{ torrents.available ? ', try fewer words, or search torrents below.' : ' or try fewer words.' }}</p>
      </div>

      <div v-if="top" class="mt-4 mb-8 grid gap-6 lg:grid-cols-[2fr_3fr]">
        <section>
          <h2 class="mb-3 text-2xl font-bold">Top result</h2>
          <RouterLink :to="top.to" class="group relative block rounded-lg bg-white/5 p-5 transition-colors hover:bg-white/10">
            <Cover :src="top.image" :round="top.round" :icon="top.kind === 'artist' ? 'artist' : 'music'" class="mb-5 h-24 w-24 shadow-lg shadow-black/50" />
            <div class="truncate text-3xl font-bold">{{ top.title }}</div>
            <div class="mt-1 truncate text-sm text-muted">{{ top.label }}</div>
            <div class="absolute right-5 bottom-5 transition-all" :class="topPlaying ? '' : 'md:translate-y-2 md:opacity-0 md:group-hover:translate-y-0 md:group-hover:opacity-100'">
              <PlayButton :playing="topPlaying" class="shadow-xl shadow-black/50" @click.prevent.stop="playTop" />
            </div>
          </RouterLink>
        </section>
        <section v-if="results.tracks.length">
          <h2 class="mb-3 text-2xl font-bold">Songs</h2>
          <TrackList :tracks="results.tracks.slice(0, 4)" :source="source" :header="false" compact />
        </section>
      </div>

      <section v-if="results.artists.length" class="mb-8">
        <h2 class="mb-2 text-2xl font-bold">Artists</h2>
        <div class="-mx-3 grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))]">
          <Card
            v-for="a in results.artists"
            :key="a.id"
            :to="`/artist/${a.id}`"
            :title="a.name"
            subtitle="Artist"
            round
            icon="artist"
            :playing="player.isPlayingSource(`/artist/${a.id}`)"
            @play="player.playCollection('artist', a.id)"
          />
        </div>
      </section>

      <section v-if="results.albums.length" class="mb-8">
        <h2 class="mb-2 text-2xl font-bold">Albums</h2>
        <div class="-mx-3 grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))]">
          <Card
            v-for="a in results.albums"
            :key="a.id"
            :to="`/album/${a.id}`"
            :image="coverUrl(a)"
            :title="a.title"
            :subtitle="[a.year, a.artist?.name].filter(Boolean).join(' · ')"
            :playing="player.isPlayingSource(`/album/${a.id}`)"
            @play="player.playCollection('album', a.id)"
          />
        </div>
      </section>

      <section v-if="results.tracks.length > 4" class="mb-8">
        <h2 class="mb-2 text-2xl font-bold">All songs</h2>
        <TrackList :tracks="results.tracks" :source="source" />
      </section>

      <TorrentSearch v-if="torrents.available" :key="query" :q="query" />
    </template>
  </div>
</template>
