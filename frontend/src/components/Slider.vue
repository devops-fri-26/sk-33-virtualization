<script setup>
import { computed, ref } from 'vue'

// Thin Spotify-style slider (seek bar / volume). Emits `input` while dragging and `commit` on release.
const props = defineProps({ value: { type: Number, default: 0 }, max: { type: Number, default: 1 }, label: { type: String, default: '' } })
const emit = defineEmits(['input', 'commit'])
const bar = ref(null)
const drag = ref(null) // 0..1 while dragging
const frac = computed(() => drag.value ?? (props.max ? Math.min(1, Math.max(0, props.value / props.max)) : 0))

function at(e) {
  const r = bar.value.getBoundingClientRect()
  return Math.min(1, Math.max(0, (e.clientX - r.left) / r.width))
}
function down(e) {
  if (!props.max) return
  e.currentTarget.setPointerCapture(e.pointerId)
  drag.value = at(e)
  emit('input', drag.value * props.max)
}
function move(e) {
  if (drag.value === null) return
  drag.value = at(e)
  emit('input', drag.value * props.max)
}
function up() {
  if (drag.value === null) return
  emit('commit', drag.value * props.max)
  drag.value = null
}
</script>

<template>
  <div
    class="group flex h-4 cursor-pointer touch-none items-center"
    role="slider"
    :aria-label="label"
    :aria-valuenow="Math.round(frac * 100)"
    aria-valuemin="0"
    aria-valuemax="100"
    @pointerdown="down"
    @pointermove="move"
    @pointerup="up"
    @pointercancel="drag = null"
  >
    <div ref="bar" class="relative h-1 w-full rounded-full bg-white/30">
      <div class="h-full rounded-full" :class="drag !== null ? 'bg-accent' : 'bg-white group-hover:bg-accent'" :style="{ width: `${frac * 100}%` }" />
      <div
        class="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow"
        :class="drag !== null ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'"
        :style="{ left: `${frac * 100}%` }"
      />
    </div>
  </div>
</template>
