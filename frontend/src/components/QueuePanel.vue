<script setup>
import { X } from 'lucide-vue-next'
import { computed } from 'vue'
import { trackCoverUrl } from '../api'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import Cover from './Cover.vue'

const p = usePlayer()
const ui = useUi()
// Tracks added with "Add to queue" come first ("Next in queue"), then the rest of the album/playlist.
const queued = computed(() => {
  const out = []
  for (const it of p.upNext) {
    if (!it.queued) break
    out.push(it)
  }
  return out
})
const rest = computed(() => p.upNext.slice(queued.value.length))
const names = (t) => t.artists.map((a) => a.name).join(', ')
</script>

<template>
  <aside class="fixed inset-0 z-50 flex flex-col bg-surface lg:static lg:z-auto lg:w-80 lg:shrink-0 lg:rounded-lg">
    <header class="flex items-center justify-between px-4 py-4">
      <h2 class="text-lg font-bold">Queue</h2>
      <button class="rounded-full p-1 text-muted hover:bg-white/10 hover:text-white" title="Close" @click="ui.queueOpen = false"><X class="h-5 w-5" /></button>
    </header>
    <div class="flex-1 overflow-y-auto px-2 pb-4">
      <template v-if="p.current">
        <h3 class="px-2 pb-2 font-bold">Now playing</h3>
        <div class="flex items-center gap-3 rounded-md p-2">
          <Cover :src="trackCoverUrl(p.current)" class="h-12 w-12 shrink-0" />
          <div class="min-w-0">
            <div class="truncate text-accent">{{ p.current.title }}</div>
            <div class="truncate text-sm text-muted">{{ names(p.current) }}</div>
          </div>
        </div>

        <template v-for="(group, g) in [queued, rest]" :key="g">
          <h3 v-if="group.length" class="px-2 pt-6 pb-2 font-bold">
            <template v-if="g === 0">Next in queue</template>
            <template v-else>
              Next<span v-if="p.source" class="font-normal text-muted"> from: <RouterLink :to="p.source.to" class="font-bold text-white hover:underline">{{ p.source.label }}</RouterLink></span>
            </template>
          </h3>
          <div
            v-for="(it, k) in group"
            :key="it.uid"
            class="group flex cursor-pointer items-center gap-3 rounded-md p-2 hover:bg-white/10"
            :title="`Play ${it.track.title}`"
            @click="p.jumpTo(p.pos + 1 + (g ? queued.length : 0) + k)"
          >
            <Cover :src="trackCoverUrl(it.track)" class="h-12 w-12 shrink-0" />
            <div class="min-w-0 flex-1">
              <div class="truncate">{{ it.track.title }}</div>
              <div class="truncate text-sm text-muted">{{ names(it.track) }}</div>
            </div>
            <button
              class="rounded-full p-1 text-muted hover:bg-white/10 hover:text-white lg:opacity-0 lg:group-hover:opacity-100"
              title="Remove from queue"
              @click.stop="p.removeAt(p.pos + 1 + (g ? queued.length : 0) + k)"
            >
              <X class="h-4 w-4" />
            </button>
          </div>
        </template>
        <p v-if="!p.upNext.length" class="px-2 pt-6 text-sm text-muted">Nothing up next. Use “Add to queue” on any song.</p>
      </template>
      <p v-else class="px-2 text-muted">Nothing playing yet. Play a song and it will show up here.</p>
    </div>
  </aside>
</template>
