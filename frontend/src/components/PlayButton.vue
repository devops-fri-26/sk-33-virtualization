<script setup>
import { Pause, Play } from 'lucide-vue-next'

defineProps({ playing: Boolean, size: { type: String, default: 'md' } }) // size: sm | md | lg
const sizes = { sm: 'h-9 w-9', md: 'h-12 w-12', lg: 'h-14 w-14' }
</script>

<template>
  <button
    class="flex shrink-0 items-center justify-center rounded-full bg-accent text-black transition hover:scale-105 hover:brightness-110 active:scale-95"
    :class="sizes[size]"
    :title="playing ? 'Pause' : 'Play'"
  >
    <Pause v-if="playing" class="h-1/2 w-1/2 fill-current" />
    <Play v-else class="ml-0.5 h-1/2 w-1/2 fill-current" />
  </button>
</template>
