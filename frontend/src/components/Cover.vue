<script setup>
import { ListMusic, Music, User } from 'lucide-vue-next'
import { ref, watch } from 'vue'

// Cover image with a placeholder icon when there is no image (or it fails to load).
const props = defineProps({ src: { type: String, default: null }, round: Boolean, icon: { type: String, default: 'music' } })
const icons = { music: Music, artist: User, playlist: ListMusic }
const failed = ref(false)
watch(() => props.src, () => (failed.value = false))
</script>

<template>
  <img v-if="src && !failed" :src="src" alt="" loading="lazy" class="bg-highlight object-cover" :class="round ? 'rounded-full' : 'rounded'" @error="failed = true" />
  <div v-else class="flex items-center justify-center bg-linear-to-br from-neutral-700 to-neutral-900 text-neutral-400" :class="round ? 'rounded-full' : 'rounded'">
    <component :is="icons[icon]" class="h-2/5 w-2/5" />
  </div>
</template>
