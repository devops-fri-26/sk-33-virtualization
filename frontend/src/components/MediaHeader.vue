<script setup>
import { computed } from 'vue'
import { useCoverColor } from '../composables/coverColor'
import Cover from './Cover.vue'

// Big gradient header for album / artist / playlist pages. Slots: title (optional), meta, actions.
const props = defineProps({
  type: { type: String, required: true },
  title: { type: String, required: true },
  image: { type: String, default: null },
  round: Boolean,
  icon: { type: String, default: 'music' },
})
const color = useCoverColor(() => props.image, () => props.title)
const background = computed(() => `linear-gradient(to bottom, rgb(${color.value}) 0%, rgb(${color.value} / 0.5) 60%, transparent 100%)`)
const size = computed(() =>
  props.title.length > 40 ? 'text-3xl md:text-5xl' : props.title.length > 16 ? 'text-4xl md:text-6xl' : 'text-5xl md:text-8xl',
)
</script>

<template>
  <div :style="{ backgroundImage: background }">
    <header class="flex flex-col items-center gap-6 px-4 pt-16 pb-6 md:flex-row md:items-end md:px-6">
      <Cover :src="image" :round="round" :icon="icon" class="h-48 w-48 shrink-0 shadow-2xl shadow-black/60 md:h-56 md:w-56" />
      <div class="w-full min-w-0">
        <p class="text-sm font-semibold">{{ type }}</p>
        <slot name="title">
          <h1 class="my-2 line-clamp-2 font-black tracking-tight break-words" :class="size">{{ title }}</h1>
        </slot>
        <div class="flex flex-wrap items-center gap-1 text-sm text-white/80"><slot name="meta" /></div>
      </div>
    </header>
    <div class="flex items-center gap-6 px-4 py-5 md:px-6"><slot name="actions" /></div>
  </div>
</template>
