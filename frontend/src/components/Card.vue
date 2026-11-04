<script setup>
import Cover from './Cover.vue'
import PlayButton from './PlayButton.vue'

// Album / artist / playlist card with a play button that slides in on hover.
defineProps({
  to: { type: String, required: true },
  image: { type: String, default: null },
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  round: Boolean,
  icon: { type: String, default: 'music' },
  playing: Boolean,
})
const emit = defineEmits(['play'])
</script>

<template>
  <RouterLink :to="to" class="group rounded-md p-3 transition-colors hover:bg-white/10">
    <div class="relative mb-3">
      <Cover :src="image" :round="round" :icon="icon" class="aspect-square w-full shadow-lg shadow-black/50" />
      <div
        class="absolute right-2 bottom-2 hidden transition-all md:block"
        :class="playing ? 'opacity-100' : 'translate-y-2 opacity-0 group-hover:translate-y-0 group-hover:opacity-100'"
      >
        <PlayButton :playing="playing" class="shadow-xl shadow-black/50" @click.prevent.stop="emit('play')" />
      </div>
    </div>
    <div class="truncate font-semibold">{{ title }}</div>
    <div class="mt-1 line-clamp-2 text-sm text-muted">{{ subtitle }}</div>
  </RouterLink>
</template>
