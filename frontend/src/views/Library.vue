<script setup>
import { Plus } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import Card from '../components/Card.vue'
import { usePlayer } from '../stores/player'
import { usePlaylists } from '../stores/playlists'

const router = useRouter()
const player = usePlayer()
const playlists = usePlaylists()
playlists.load()

async function create() {
  const pl = await playlists.createNext()
  router.push(`/playlist/${pl.id}`)
}
</script>

<template>
  <div class="px-4 pt-16 pb-10 md:px-6">
    <div class="mb-6 flex flex-wrap items-center justify-between gap-4">
      <h1 class="text-3xl font-bold">Your Library</h1>
      <button class="flex items-center gap-2 rounded-full bg-white px-5 py-2 font-bold text-black hover:scale-105" @click="create">
        <Plus class="h-5 w-5" /> Create playlist
      </button>
    </div>
    <div v-if="playlists.list.length" class="-mx-3 grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))]">
      <Card
        v-for="pl in playlists.list"
        :key="pl.id"
        :to="`/playlist/${pl.id}`"
        icon="playlist"
        :title="pl.name"
        :subtitle="`Playlist · ${pl.count} ${pl.count === 1 ? 'song' : 'songs'}`"
        :playing="player.isPlayingSource(`/playlist/${pl.id}`)"
        @play="player.playCollection('playlist', pl.id)"
      />
    </div>
    <p v-else class="mt-10 text-center text-muted">No playlists yet. Create one and add songs with the ⊕ button.</p>
  </div>
</template>
