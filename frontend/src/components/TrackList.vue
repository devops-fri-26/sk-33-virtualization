<script setup>
import {
  ArrowDown, ArrowUp, CirclePlus, Clock3, Download, Ellipsis, ListMusic, ListPlus, ListX, Pause, Pencil, Play, Trash2, TriangleAlert,
} from 'lucide-vue-next'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, fmtTime, trackCoverUrl } from '../api'
import { useAuth } from '../stores/auth'
import { usePlayer } from '../stores/player'
import { usePlaylists } from '../stores/playlists'
import { useUi } from '../stores/ui'
import Cover from './Cover.vue'
import TrackEditor from './TrackEditor.vue'

// Spotify-style track table.
// `album` mode hides covers and the album column and shows track numbers;
// `compact` hides the album column (narrow lists); `playlist` adds move/remove actions (tracks carry `entry_id`).
const props = defineProps({
  tracks: { type: Array, required: true },
  source: { type: Object, default: null }, // { label, to } shown as "Next from" in the queue
  album: Boolean,
  compact: Boolean,
  playlist: Boolean,
  header: { type: Boolean, default: true },
})
const emit = defineEmits(['move', 'remove'])
const auth = useAuth()
const player = usePlayer()
const playlists = usePlaylists()
const ui = useUi()
const editing = ref(null)
const menu = ref(null) // { track, index, style, pick }
const MENU_W = 240

const albumColumn = computed(() => !props.album && !props.compact)
const cols = computed(() =>
  !albumColumn.value
    ? 'grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[1rem_minmax(0,1fr)_auto]'
    : 'grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[1rem_minmax(0,4fr)_minmax(0,3fr)_auto]',
)
const isCurrent = (t) => player.current?.id === t.id
const isTouch = () => matchMedia('(hover: none)').matches
const item = 'flex w-full items-center gap-3 rounded-sm px-3 py-2.5 text-left hover:bg-white/10 disabled:opacity-40 disabled:hover:bg-transparent'

function play(i) {
  if (isCurrent(props.tracks[i]) && player.source?.to === props.source?.to) return player.toggle()
  player.playQueue(props.tracks, i, props.source)
}

function openMenu(e, track, index, pick = false) {
  const ctx = e.type === 'contextmenu'
  const r = ctx ? { left: e.clientX, top: e.clientY, bottom: e.clientY } : e.currentTarget.getBoundingClientRect()
  const left = Math.max(8, Math.min(ctx ? r.left : r.right - MENU_W, innerWidth - MENU_W - 8))
  const vertical = r.bottom < innerHeight * 0.55 ? { top: `${r.bottom + 4}px` } : { bottom: `${innerHeight - r.top + 4}px` }
  menu.value = { track, index, pick, style: { left: `${left}px`, width: `${MENU_W}px`, ...vertical } }
  playlists.load()
}
const closeMenu = () => (menu.value = null)
const onKey = (e) => e.key === 'Escape' && closeMenu()
onMounted(() => addEventListener('keydown', onKey))
onUnmounted(() => removeEventListener('keydown', onKey))

function queueTrack() {
  player.addToQueue(menu.value.track)
  ui.notify('Added to queue')
  closeMenu()
}
function editTrack() {
  editing.value = menu.value.track
  closeMenu()
}
function moveTrack(dir) {
  emit('move', menu.value.index, dir)
  closeMenu()
}
function removeTrack() {
  emit('remove', menu.value.track)
  closeMenu()
}
async function addTo(pl) {
  try {
    await playlists.addTrack(pl.id, menu.value.track.id)
    ui.notify(`Added to ${pl.name}`)
  } catch (e) {
    ui.notify(e.message) // e.g. the track or the playlist was deleted meanwhile
  }
  closeMenu()
}
async function deleteTrack() {
  const track = menu.value.track
  closeMenu()
  if (!confirm(`Delete "${track.title}" from the library? The file is deleted for everyone and removed from all playlists.`)) return
  try {
    await api(`/tracks/${track.id}`, { method: 'DELETE' })
  } catch (e) {
    return ui.notify(e.message)
  }
  for (let i = props.tracks.length - 1; i >= 0; i--) if (props.tracks[i].id === track.id) props.tracks.splice(i, 1)
  ui.notify('Deleted from the library')
  auth.refresh().catch(() => {}) // storage used
}
function saved(updated) {
  props.tracks.filter((t) => t.id === updated.id).forEach((t) => Object.assign(t, updated, { entry_id: t.entry_id }))
  editing.value = null
}
</script>

<template>
  <div class="text-sm">
    <div v-if="header" class="mb-2 hidden h-9 items-center gap-4 border-b border-white/10 px-4 text-muted md:grid" :class="cols">
      <span class="text-right">#</span>
      <span>Title</span>
      <span v-if="albumColumn">Album</span>
      <span class="flex justify-end pr-9"><Clock3 class="h-4 w-4" /></span>
    </div>

    <div
      v-for="(t, i) in tracks"
      :key="t.entry_id ?? t.id"
      class="group grid h-14 items-center gap-4 rounded-md px-2 select-none hover:bg-white/10 md:px-4"
      :class="[cols, { 'bg-white/10': menu?.index === i }]"
      @dblclick="play(i)"
      @contextmenu.prevent="openMenu($event, t, i)"
    >
      <!-- number / play button / now-playing bars -->
      <div class="hidden justify-end text-muted md:flex">
        <button class="hidden text-white group-hover:block" :title="isCurrent(t) && player.playing ? 'Pause' : 'Play'" @click="play(i)">
          <Pause v-if="isCurrent(t) && player.playing" class="h-4 w-4 fill-current" />
          <Play v-else class="h-4 w-4 fill-current" />
        </button>
        <span class="tabular-nums group-hover:hidden">
          <span v-if="isCurrent(t) && player.playing" class="eq"><span /><span /><span /><span /></span>
          <span v-else :class="{ 'text-accent': isCurrent(t) }">{{ album ? (t.track_no ?? i + 1) : i + 1 }}</span>
        </span>
      </div>

      <!-- title + artists -->
      <div class="flex min-w-0 items-center gap-3" @click="isTouch() && play(i)">
        <Cover v-if="!album" :src="trackCoverUrl(t)" class="h-10 w-10 shrink-0" />
        <div class="min-w-0">
          <div class="truncate text-base" :class="isCurrent(t) ? 'text-accent' : 'text-white'">{{ t.title }}</div>
          <div class="flex items-center gap-1 truncate text-muted">
            <span class="rounded-sm bg-white/15 px-1 text-[9px] leading-4 font-bold text-neutral-300 uppercase">{{ t.format }}</span>
            <template v-for="(a, j) in t.artists" :key="a.id">
              <RouterLink :to="`/artist/${a.id}`" class="hover:text-white hover:underline" @click.stop>{{ a.name }}</RouterLink>
              <span v-if="j < t.artists.length - 1" class="-ml-1">,</span>
            </template>
            <template v-if="t.needs_artists">
              <button v-if="auth.canEdit(t)" class="flex items-center gap-1 text-amber-400 hover:underline" @click.stop="editing = t">
                <TriangleAlert class="h-3.5 w-3.5" /> Add artists
              </button>
              <span v-else>Unknown artist</span>
            </template>
          </div>
        </div>
      </div>

      <!-- album -->
      <template v-if="albumColumn">
        <RouterLink v-if="t.album" :to="`/album/${t.album.id}`" class="hidden truncate text-muted hover:text-white hover:underline md:block">
          {{ t.album.title }}
        </RouterLink>
        <span v-else class="hidden md:block" />
      </template>

      <!-- actions + duration -->
      <div class="flex items-center justify-end gap-3 text-muted">
        <button class="hidden hover:text-white md:invisible md:block md:group-hover:visible" title="Add to playlist" @click="openMenu($event, t, i, true)">
          <CirclePlus class="h-4 w-4" />
        </button>
        <span class="hidden w-10 text-right tabular-nums md:block">{{ fmtTime(t.duration) }}</span>
        <button class="hover:text-white md:invisible md:group-hover:visible" title="More options" @click="openMenu($event, t, i)">
          <Ellipsis class="h-5 w-5" />
        </button>
      </div>
    </div>
  </div>

  <Teleport to="body">
    <template v-if="menu">
      <div class="fixed inset-0 z-40" @click="closeMenu" @contextmenu.prevent="closeMenu" />
      <div class="fixed z-50 max-h-[60vh] overflow-y-auto rounded-md bg-highlight p-1 text-sm shadow-2xl shadow-black/60" :style="menu.style">
        <template v-if="menu.pick">
          <p class="px-3 py-2 text-xs font-bold text-muted uppercase">Add to playlist</p>
          <button v-for="pl in playlists.list" :key="pl.id" :class="item" @click="addTo(pl)">
            <ListMusic class="h-4 w-4 shrink-0 text-muted" /><span class="truncate">{{ pl.name }}</span>
          </button>
          <p v-if="!playlists.list.length" class="px-3 py-2 text-muted">No playlists yet. Create one with + in Your Library.</p>
        </template>
        <template v-else>
          <button :class="item" @click="queueTrack">
            <ListPlus class="h-4 w-4" /> Add to queue
          </button>
          <button :class="item" @click="menu.pick = true"><CirclePlus class="h-4 w-4" /> Add to playlist</button>
          <button v-if="auth.canEdit(menu.track)" :class="item" @click="editTrack"><Pencil class="h-4 w-4" /> Edit details</button>
          <a :class="item" :href="`/api/tracks/${menu.track.id}/download`" @click="closeMenu"><Download class="h-4 w-4" /> Download</a>
          <template v-if="playlist">
            <div class="my-1 border-t border-white/10" />
            <button :class="item" :disabled="menu.index === 0" @click="moveTrack(-1)">
              <ArrowUp class="h-4 w-4" /> Move up
            </button>
            <button :class="item" :disabled="menu.index === tracks.length - 1" @click="moveTrack(1)">
              <ArrowDown class="h-4 w-4" /> Move down
            </button>
            <button :class="item" @click="removeTrack"><ListX class="h-4 w-4" /> Remove from this playlist</button>
          </template>
          <template v-if="auth.canEdit(menu.track)">
            <div class="my-1 border-t border-white/10" />
            <button :class="item" class="text-red-300" @click="deleteTrack"><Trash2 class="h-4 w-4" /> Delete from library</button>
          </template>
        </template>
      </div>
    </template>
  </Teleport>

  <TrackEditor v-if="editing" :track="editing" @close="editing = null" @saved="saved" />
</template>
