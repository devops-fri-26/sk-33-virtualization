<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, coverUrl } from '../api'
import Card from '../components/Card.vue'
import { usePlayer } from '../stores/player'

// The whole library: every album or every artist, loaded a page at a time while scrolling.
const PAGE = 60
const route = useRoute()
const router = useRouter()
const player = usePlayer()
const tab = ref(route.query.tab === 'artists' ? 'artists' : 'albums')
const sort = ref('title') // albums only: 'title' or 'recent'
const items = ref([])
const total = ref(null)
const busy = ref(false)
const error = ref('')
const more = ref(null) // the element at the end of the list; reaching it loads the next page
let seq = 0

async function load() {
  if (busy.value || (total.value !== null && items.value.length >= total.value)) return
  busy.value = true
  const n = seq
  try {
    const query = `offset=${items.value.length}&limit=${PAGE}${tab.value === 'albums' ? `&sort=${sort.value}` : ''}`
    const page = await api(`/${tab.value}?${query}`)
    if (n !== seq) return // the tab or the order changed meanwhile
    items.value.push(...page.items)
    total.value = page.items.length ? page.total : items.value.length // an empty page ends the list
    busy.value = false
    // The observer only reports changes. Watching again makes it report where the end of the list is now, so the
    // next page loads when this one didn't fill the screen.
    observer.unobserve(more.value)
    observer.observe(more.value)
  } catch (e) {
    if (n === seq) error.value = e.message
  } finally {
    if (n === seq) busy.value = false
  }
}

function show(newTab, newSort = sort.value) {
  seq++
  tab.value = newTab
  sort.value = newSort
  items.value = []
  total.value = null
  busy.value = false
  error.value = ''
  router.replace({ query: newTab === 'artists' ? { tab: 'artists' } : {} })
  load()
}

// Declared before load() can run: the first page is asked for by the observer itself.
const observer = new IntersectionObserver((entries) => entries.at(-1).isIntersecting && load())
onMounted(() => observer.observe(more.value)) // reports straight away, which loads the first page
onUnmounted(() => observer.disconnect())

const pill = (on) => ['rounded-full px-4 py-1.5 text-sm font-bold transition-colors', on ? 'bg-white text-black' : 'bg-white/10 hover:bg-white/20']
</script>

<template>
  <div class="px-4 pt-16 pb-10 md:px-6">
    <h1 class="mb-6 text-3xl font-bold">Browse</h1>
    <div class="mb-6 flex flex-wrap items-center gap-2">
      <button :class="pill(tab === 'albums')" @click="show('albums')">Albums</button>
      <button :class="pill(tab === 'artists')" @click="show('artists')">Artists</button>
      <span v-if="total !== null" class="ml-2 text-sm text-muted">{{ total }} {{ tab === 'albums' ? (total === 1 ? 'album' : 'albums') : total === 1 ? 'artist' : 'artists' }}</span>
      <select
        v-if="tab === 'albums'"
        :value="sort"
        class="ml-auto rounded-md bg-white/10 px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-white"
        title="Order"
        @change="show('albums', $event.target.value)"
      >
        <option value="title" class="bg-highlight">A to Z</option>
        <option value="recent" class="bg-highlight">Recently added</option>
      </select>
    </div>

    <div class="-mx-3 grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))]">
      <template v-if="tab === 'albums'">
        <Card
          v-for="a in items"
          :key="a.id"
          :to="`/album/${a.id}`"
          :image="coverUrl(a)"
          :title="a.title"
          :subtitle="[a.year, a.artist?.name].filter(Boolean).join(' · ')"
          :playing="player.isPlayingSource(`/album/${a.id}`)"
          @play="player.playCollection('album', a.id)"
        />
      </template>
      <template v-else>
        <Card
          v-for="a in items"
          :key="a.id"
          :to="`/artist/${a.id}`"
          :title="a.name"
          subtitle="Artist"
          round
          icon="artist"
          :playing="player.isPlayingSource(`/artist/${a.id}`)"
          @play="player.playCollection('artist', a.id)"
        />
      </template>
    </div>

    <p v-if="error" class="mt-6 text-red-400">{{ error }}</p>
    <p v-else-if="total === 0" class="mt-10 text-center text-muted">Nothing here yet. Upload some music to fill the library.</p>
    <div ref="more" class="h-px" />
  </div>
</template>
