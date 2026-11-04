<script setup>
import { Shuffle } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, coverUrl } from '../api'
import Card from '../components/Card.vue'
import MediaHeader from '../components/MediaHeader.vue'
import PlayButton from '../components/PlayButton.vue'
import TrackList from '../components/TrackList.vue'
import { usePlayer } from '../stores/player'

const id = useRoute().params.id
const player = usePlayer()
const artist = ref(null)
const error = ref('')
api(`/artists/${id}`).then((a) => (artist.value = a)).catch((e) => (error.value = e.message))

const source = computed(() => ({ label: artist.value?.name, to: `/artist/${id}` }))
</script>

<template>
  <div v-if="artist" class="pb-10">
    <MediaHeader type="Artist" :title="artist.name" round icon="artist">
      <template #meta>
        <span>{{ artist.tracks.length }} {{ artist.tracks.length === 1 ? 'song' : 'songs' }}</span>
        <span v-if="artist.albums.length">· {{ artist.albums.length }} {{ artist.albums.length === 1 ? 'album' : 'albums' }}</span>
      </template>
      <template #actions>
        <PlayButton size="lg" :playing="player.isPlayingSource(source.to)" @click="player.playSource(artist.tracks, source)" />
        <button :class="player.shuffle ? 'text-accent' : 'text-muted hover:text-white'" :title="player.shuffle ? 'Disable shuffle' : 'Enable shuffle'" @click="player.toggleShuffle">
          <Shuffle class="h-8 w-8" />
        </button>
      </template>
    </MediaHeader>
    <section class="px-4 md:px-6">
      <h2 class="mb-2 text-2xl font-bold">Songs</h2>
      <TrackList :tracks="artist.tracks" :source="source" />
    </section>
    <section v-if="artist.albums.length" class="mt-10 px-4 md:px-6">
      <h2 class="mb-2 text-2xl font-bold">Discography</h2>
      <div class="-mx-3 grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))]">
        <Card
          v-for="a in artist.albums"
          :key="a.id"
          :to="`/album/${a.id}`"
          :image="coverUrl(a)"
          :title="a.title"
          :subtitle="a.year ? `${a.year} · Album` : 'Album'"
          :playing="player.isPlayingSource(`/album/${a.id}`)"
          @play="player.playCollection('album', a.id)"
        />
      </div>
    </section>
  </div>
  <p v-else-if="error" class="px-6 pt-16 text-muted">{{ error }}</p>
</template>
