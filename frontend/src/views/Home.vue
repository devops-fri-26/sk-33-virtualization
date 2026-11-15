<script setup>
import { TriangleAlert, Upload } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { api, coverUrl } from '../api'
import Card from '../components/Card.vue'
import Cover from '../components/Cover.vue'
import PlayButton from '../components/PlayButton.vue'
import TrackList from '../components/TrackList.vue'
import { usePlayer } from '../stores/player'
import { usePlaylists } from '../stores/playlists'

const player = usePlayer()
const playlists = usePlaylists()
const recent = ref(null)
const missing = ref([])
const showMissing = ref(false)
const hour = new Date().getHours()
const greeting = hour >= 5 && hour < 12 ? 'Good morning' : hour >= 12 && hour < 18 ? 'Good afternoon' : 'Good evening'

// Albums of the most recently added tracks, newest first.
const albums = computed(() => {
  const seen = new Map()
  for (const t of recent.value ?? []) if (t.album && !seen.has(t.album.id)) seen.set(t.album.id, t.album)
  return [...seen.values()].slice(0, 12)
})

onMounted(async () => {
  playlists.load()
  ;[recent.value, missing.value] = await Promise.all([
    api('/search?q=').then((r) => r.tracks),
    api('/tracks?needs_artists=true'),
  ])
})
</script>

<template>
  <div class="min-h-full px-4 pt-16 pb-10 md:px-6" style="background: linear-gradient(to bottom, rgb(32 72 52) 0, var(--color-surface) 320px)">
    <h1 class="mb-6 text-3xl font-bold">{{ greeting }}</h1>

    <div v-if="playlists.list.length" class="mb-8 grid grid-cols-2 gap-2 lg:grid-cols-4">
      <RouterLink
        v-for="pl in playlists.list.slice(0, 8)"
        :key="pl.id"
        :to="`/playlist/${pl.id}`"
        class="group flex h-14 items-center gap-3 overflow-hidden rounded-md bg-white/10 pr-2 transition-colors hover:bg-white/20"
      >
        <Cover icon="playlist" class="h-14 w-14 shrink-0 rounded-none" />
        <span class="min-w-0 flex-1 truncate text-sm font-bold">{{ pl.name }}</span>
        <span class="hidden md:block" :class="player.isPlayingSource(`/playlist/${pl.id}`) ? '' : 'md:invisible md:group-hover:visible'">
          <PlayButton size="sm" class="shadow-lg" :playing="player.isPlayingSource(`/playlist/${pl.id}`)" @click.prevent.stop="player.playCollection('playlist', pl.id)" />
        </span>
      </RouterLink>
    </div>

    <div v-if="missing.length" class="mb-8 rounded-lg bg-amber-500/10 p-4 ring-1 ring-amber-500/30">
      <button class="flex items-center gap-2 text-left font-semibold text-amber-300" @click="showMissing = !showMissing">
        <TriangleAlert class="h-5 w-5 shrink-0" />
        {{ missing.length }} {{ missing.length === 1 ? 'song has' : 'songs have' }} no artist. {{ showMissing ? 'Hide' : 'Add them' }}
      </button>
      <TrackList v-if="showMissing" class="mt-3" :tracks="missing" :header="false" />
    </div>

    <section v-if="albums.length" class="mb-8">
      <h2 class="mb-2 text-2xl font-bold">Recently added albums</h2>
      <div class="-mx-3 grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))]">
        <Card
          v-for="a in albums"
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

    <section v-if="recent?.length">
      <h2 class="mb-2 text-2xl font-bold">Recently added songs</h2>
      <TrackList :tracks="recent.slice(0, 20)" :source="{ label: 'Recently added', to: '/' }" />
    </section>
    <div v-else-if="recent" class="mt-20 flex flex-col items-center text-center">
      <Upload class="mb-4 h-14 w-14 text-muted" />
      <h2 class="text-2xl font-bold">Your library is empty</h2>
      <p class="mt-2 text-muted">Upload your music to get started.</p>
      <div class="mt-6 flex gap-3">
        <RouterLink to="/upload" class="rounded-full bg-white px-6 py-3 font-bold text-black hover:scale-105">Upload music</RouterLink>
        <RouterLink to="/search" class="rounded-full border border-white/30 px-6 py-3 font-bold hover:border-white">Search</RouterLink>
      </div>
    </div>
  </div>
</template>
