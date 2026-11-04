<script setup>
import { AudioLines, Download, House, Library, Plus, Search, Upload, Volume2 } from 'lucide-vue-next'
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlayer } from '../stores/player'
import { usePlaylists } from '../stores/playlists'
import Cover from './Cover.vue'

const nav = [
  { to: '/', label: 'Home', icon: House },
  { to: '/search', label: 'Search', icon: Search },
  { to: '/upload', label: 'Upload', icon: Upload },
  { to: '/torrents', label: 'Torrents', icon: Download },
]
const route = useRoute()
const router = useRouter()
const player = usePlayer()
const playlists = usePlaylists()
onMounted(playlists.load)

async function create() {
  const pl = await playlists.createNext()
  router.push(`/playlist/${pl.id}`)
}
</script>

<template>
  <aside class="flex flex-col gap-2">
    <nav class="rounded-lg bg-surface px-3 py-4">
      <RouterLink to="/" class="mb-3 flex items-center gap-2 px-3 text-2xl font-extrabold tracking-tight">
        <AudioLines class="h-7 w-7 text-accent" /> Varsis
      </RouterLink>
      <RouterLink
        v-for="n in nav"
        :key="n.to"
        :to="n.to"
        class="flex items-center gap-4 rounded-md px-3 py-2.5 font-bold transition-colors"
        :class="route.path === n.to ? 'text-white' : 'text-muted hover:text-white'"
      >
        <component :is="n.icon" class="h-6 w-6" /> {{ n.label }}
      </RouterLink>
    </nav>

    <section class="flex min-h-0 flex-1 flex-col rounded-lg bg-surface">
      <header class="flex items-center justify-between px-6 pt-4 pb-2 text-muted">
        <RouterLink to="/library" class="flex items-center gap-3 font-bold transition-colors hover:text-white">
          <Library class="h-6 w-6" /> Your Library
        </RouterLink>
        <button class="rounded-full p-1.5 transition-colors hover:bg-white/10 hover:text-white" title="Create playlist" @click="create">
          <Plus class="h-5 w-5" />
        </button>
      </header>
      <div class="flex-1 overflow-y-auto px-2 pb-2">
        <RouterLink
          v-for="pl in playlists.list"
          :key="pl.id"
          :to="`/playlist/${pl.id}`"
          class="flex items-center gap-3 rounded-md p-2 transition-colors hover:bg-white/10"
          active-class="bg-white/10"
        >
          <Cover icon="playlist" class="h-12 w-12 shrink-0" />
          <div class="min-w-0 flex-1">
            <div class="truncate" :class="{ 'text-accent': player.source?.to === `/playlist/${pl.id}` }">{{ pl.name }}</div>
            <div class="truncate text-sm text-muted">Playlist · {{ pl.count }} {{ pl.count === 1 ? 'song' : 'songs' }}</div>
          </div>
          <Volume2 v-if="player.isPlayingSource(`/playlist/${pl.id}`)" class="h-4 w-4 shrink-0 text-accent" />
        </RouterLink>
        <div v-if="!playlists.list.length" class="m-2 rounded-lg bg-highlight p-4">
          <p class="font-bold">Create your first playlist</p>
          <p class="mt-1 text-sm text-muted">Collect your favourite songs in one place.</p>
          <button class="mt-4 rounded-full bg-white px-4 py-1.5 text-sm font-bold text-black hover:scale-105" @click="create">Create playlist</button>
        </div>
      </div>
    </section>
  </aside>
</template>
