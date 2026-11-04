<script setup>
import { X } from 'lucide-vue-next'
import { ref } from 'vue'
import { api } from '../api'

const props = defineProps({ track: { type: Object, required: true } })
const emit = defineEmits(['close', 'saved'])
const names = ref(props.track.artists.map((a) => a.name))
const input = ref('')
const suggestions = ref([])
const error = ref('')

async function suggest() {
  const q = input.value.trim()
  suggestions.value = q ? (await api(`/search?q=${encodeURIComponent(q)}`)).artists : []
}
function add() {
  const n = input.value.trim()
  if (n && !names.value.includes(n)) names.value.push(n)
  input.value = ''
  suggestions.value = []
}
async function save() {
  add()
  try {
    emit('saved', await api(`/tracks/${props.track.id}/artists`, { method: 'PUT', body: { names: names.value } }))
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" @click.self="emit('close')">
      <div class="w-full max-w-md rounded-xl bg-highlight p-6 shadow-2xl">
        <div class="mb-1 flex items-center justify-between">
          <h2 class="text-2xl font-bold">Edit artists</h2>
          <button class="rounded-full p-1 text-muted hover:bg-white/10 hover:text-white" title="Close" @click="emit('close')"><X class="h-5 w-5" /></button>
        </div>
        <p class="mb-5 truncate text-sm text-muted">{{ track.title }}</p>
        <div class="mb-3 flex min-h-8 flex-wrap gap-2">
          <span v-for="(n, i) in names" :key="n" class="flex items-center gap-1 rounded-full bg-white/10 py-1 pr-1.5 pl-3 text-sm">
            {{ n }}
            <button class="rounded-full p-0.5 text-muted hover:bg-white/10 hover:text-white" :title="`Remove ${n}`" @click="names.splice(i, 1)"><X class="h-3.5 w-3.5" /></button>
          </span>
          <span v-if="!names.length" class="text-sm text-muted">No artists yet.</span>
        </div>
        <form class="flex gap-2" @submit.prevent="add">
          <input
            v-model="input"
            list="artist-suggestions"
            placeholder="Artist name"
            class="flex-1 rounded-md bg-white/10 px-3 py-2 outline-none placeholder:text-muted focus:ring-2 focus:ring-white"
            @input="suggest"
          />
          <datalist id="artist-suggestions">
            <option v-for="a in suggestions" :key="a.id" :value="a.name" />
          </datalist>
          <button class="rounded-full border border-white/30 px-4 text-sm font-bold hover:border-white">Add</button>
        </form>
        <p v-if="error" class="mt-2 text-sm text-red-400">{{ error }}</p>
        <div class="mt-6 flex justify-end gap-3">
          <button class="px-4 py-2 font-bold text-muted hover:text-white" @click="emit('close')">Cancel</button>
          <button class="rounded-full bg-white px-6 py-2 font-bold text-black hover:scale-105" @click="save">Save</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
