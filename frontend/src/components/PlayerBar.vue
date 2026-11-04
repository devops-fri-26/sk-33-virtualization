<script setup>
import { ListMusic, Pause, Play, Repeat, Repeat1, Shuffle, SkipBack, SkipForward, Volume1, Volume2, VolumeX } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { coverUrl, fmtTime } from '../api'
import { useCoverColor } from '../composables/coverColor'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import Cover from './Cover.vue'
import Slider from './Slider.vue'

const p = usePlayer()
const ui = useUi()
const scrub = ref(null) // seek position while dragging the progress bar
const shown = computed(() => scrub.value ?? p.time)
const cover = computed(() => coverUrl(p.current?.album))
const artists = computed(() => p.current?.artists ?? [])
const color = useCoverColor(() => cover.value, () => p.current?.title ?? '')
const VolumeIcon = computed(() => (p.muted || p.volume === 0 ? VolumeX : p.volume < 0.5 ? Volume1 : Volume2))

// Active toggle buttons are green with a small dot underneath, like Spotify.
const toggleClass = (on) =>
  on
    ? 'relative text-accent after:absolute after:-bottom-2 after:left-1/2 after:h-1 after:w-1 after:-translate-x-1/2 after:rounded-full after:bg-accent'
    : 'text-muted hover:text-white'

function commitSeek(v) {
  p.seek(v)
  scrub.value = null
}
</script>

<template>
  <!-- desktop -->
  <footer class="hidden h-[72px] shrink-0 grid-cols-[minmax(0,1fr)_minmax(0,2fr)_minmax(0,1fr)] items-center gap-4 px-2 md:grid">
    <div class="flex min-w-0 items-center gap-3">
      <template v-if="p.current">
        <RouterLink :to="p.current.album ? `/album/${p.current.album.id}` : '/'" class="shrink-0">
          <Cover :src="cover" class="h-14 w-14" />
        </RouterLink>
        <div class="min-w-0">
          <div class="truncate text-sm font-medium">{{ p.current.title }}</div>
          <div class="truncate text-xs text-muted">
            <template v-for="(a, j) in artists" :key="a.id">
              <RouterLink :to="`/artist/${a.id}`" class="hover:text-white hover:underline">{{ a.name }}</RouterLink><span v-if="j < artists.length - 1">, </span>
            </template>
          </div>
        </div>
      </template>
    </div>

    <div class="flex flex-col items-center gap-1">
      <div class="flex items-center gap-6">
        <button :class="toggleClass(p.shuffle)" :title="p.shuffle ? 'Disable shuffle' : 'Enable shuffle'" @click="p.toggleShuffle"><Shuffle class="h-4 w-4" /></button>
        <button class="text-muted hover:text-white" title="Previous (Shift+←)" @click="p.prev"><SkipBack class="h-5 w-5 fill-current" /></button>
        <button
          class="flex h-8 w-8 items-center justify-center rounded-full bg-white text-black transition hover:scale-105 disabled:opacity-50"
          :disabled="!p.current"
          :title="p.playing ? 'Pause (Space)' : 'Play (Space)'"
          @click="p.toggle"
        >
          <Pause v-if="p.playing" class="h-4 w-4 fill-current" />
          <Play v-else class="ml-0.5 h-4 w-4 fill-current" />
        </button>
        <button class="text-muted hover:text-white" title="Next (Shift+→)" @click="p.next"><SkipForward class="h-5 w-5 fill-current" /></button>
        <button :class="toggleClass(p.repeat !== 'off')" :title="`Repeat: ${p.repeat}`" @click="p.cycleRepeat">
          <Repeat1 v-if="p.repeat === 'one'" class="h-4 w-4" />
          <Repeat v-else class="h-4 w-4" />
        </button>
      </div>
      <div class="flex w-full max-w-2xl items-center gap-2 text-xs text-muted tabular-nums">
        <span class="w-10 text-right">{{ fmtTime(shown) }}</span>
        <Slider class="flex-1" :value="shown" :max="p.duration || 0" label="Seek" @input="scrub = $event" @commit="commitSeek" />
        <span class="w-10">{{ fmtTime(p.duration) }}</span>
      </div>
    </div>

    <div class="flex items-center justify-end gap-3">
      <span v-if="p.current" class="rounded-sm border border-white/25 px-1.5 text-[10px] font-bold tracking-wider text-muted uppercase" title="File format (played without conversion)">
        {{ p.current.format }}
      </span>
      <button :class="toggleClass(ui.queueOpen)" title="Queue" @click="ui.queueOpen = !ui.queueOpen"><ListMusic class="h-4 w-4" /></button>
      <button class="text-muted hover:text-white" :title="p.muted ? 'Unmute' : 'Mute'" @click="p.toggleMute"><component :is="VolumeIcon" class="h-4 w-4" /></button>
      <Slider class="w-24" :value="p.muted ? 0 : p.volume" :max="1" label="Volume" @input="p.setVolume" @commit="p.setVolume" />
    </div>
  </footer>

  <!-- phone: mini player -->
  <div v-if="p.current" class="relative mx-2 mb-1 flex items-center gap-3 rounded-md p-2 pb-3 md:hidden" :style="{ backgroundColor: `rgb(${color})` }">
    <Cover :src="cover" class="h-10 w-10 shrink-0" />
    <div class="min-w-0 flex-1 text-sm">
      <div class="truncate font-medium">{{ p.current.title }}</div>
      <div class="truncate text-white/70">{{ artists.map((a) => a.name).join(', ') }}</div>
    </div>
    <button class="p-1" title="Queue" @click="ui.queueOpen = true"><ListMusic class="h-5 w-5" /></button>
    <button class="p-1" :title="p.playing ? 'Pause' : 'Play'" @click="p.toggle">
      <Pause v-if="p.playing" class="h-6 w-6 fill-current" />
      <Play v-else class="h-6 w-6 fill-current" />
    </button>
    <button class="p-1" title="Next" @click="p.next"><SkipForward class="h-6 w-6 fill-current" /></button>
    <Slider class="absolute inset-x-2 -bottom-1.5" :value="shown" :max="p.duration || 0" label="Seek" @input="scrub = $event" @commit="commitSeek" />
  </div>
</template>
