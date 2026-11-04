<script setup>
import { Shuffle } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, coverUrl, fmtTotal } from '../api'
import MediaHeader from '../components/MediaHeader.vue'
import PlayButton from '../components/PlayButton.vue'
import TrackList from '../components/TrackList.vue'
import { usePlayer } from '../stores/player'

const id = useRoute().params.id
const player = usePlayer()
const album = ref(null)
const error = ref('')
api(`/albums/${id}`).then((a) => (album.value = a)).catch((e) => (error.value = e.message))

const source = computed(() => ({ label: album.value?.title, to: `/album/${id}` }))
const total = computed(() => album.value.tracks.reduce((s, t) => s + t.duration, 0))
</script>

<template>
  <div v-if="album" class="pb-10">
    <MediaHeader type="Album" :title="album.title" :image="coverUrl(album)">
      <template #meta>
        <RouterLink v-if="album.artist" :to="`/artist/${album.artist.id}`" class="font-bold text-white hover:underline">{{ album.artist.name }}</RouterLink>
        <span v-if="album.year">· {{ album.year }}</span>
        <span>· {{ album.tracks.length }} {{ album.tracks.length === 1 ? 'song' : 'songs' }}, {{ fmtTotal(total) }}</span>
      </template>
      <template #actions>
        <PlayButton size="lg" :playing="player.isPlayingSource(source.to)" @click="player.playSource(album.tracks, source)" />
        <button :class="player.shuffle ? 'text-accent' : 'text-muted hover:text-white'" :title="player.shuffle ? 'Disable shuffle' : 'Enable shuffle'" @click="player.toggleShuffle">
          <Shuffle class="h-8 w-8" />
        </button>
      </template>
    </MediaHeader>
    <TrackList class="px-2 md:px-6" album :tracks="album.tracks" :source="source" />
  </div>
  <p v-else-if="error" class="px-6 pt-16 text-muted">{{ error }}</p>
</template>
