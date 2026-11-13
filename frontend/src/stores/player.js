// Player: Spotify-style queue (shuffle, repeat, "add to queue" plays next), volume, Media Session,
// and a prefetch cache that downloads the next tracks to the device so they start without lag.
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, streamUrl, trackCoverUrl } from '../api'
import { useUi } from './ui'

const PREFETCH_AHEAD = 2
const CACHE_NAME = 'tracks'
const MAX_TRACKS = 30
const MAX_BYTES = 1024 ** 3 // 1 GB
const META_KEY = 'trackCacheMeta' // { [id]: { t: lastUsed, size } } for LRU eviction
const VOLUME_KEY = 'volume'
const ENDPOINT = { album: 'albums', artist: 'artists', playlist: 'playlists' }
const hasCache = typeof caches !== 'undefined' // Cache API needs https or localhost

// ---------- prefetch cache (LRU) ----------

function readMeta() {
  try { return JSON.parse(localStorage.getItem(META_KEY)) || {} } catch { return {} }
}
function writeMeta(meta) {
  try { localStorage.setItem(META_KEY, JSON.stringify(meta)) } catch { /* storage unavailable */ }
}
function touch(id, size) {
  const meta = readMeta()
  meta[id] = { t: Date.now(), size: size ?? meta[id]?.size ?? 0 }
  writeMeta(meta)
}

async function cachedBlobUrl(id) {
  if (!hasCache) return null
  const res = await (await caches.open(CACHE_NAME)).match(streamUrl(id))
  if (!res) return null
  touch(id)
  return URL.createObjectURL(await res.blob())
}

const pending = new Set()
async function prefetch(track, keep) {
  if (!hasCache || pending.has(track.id)) return
  const cache = await caches.open(CACHE_NAME)
  if (await cache.match(streamUrl(track.id))) return touch(track.id)
  pending.add(track.id)
  try {
    const res = await fetch(streamUrl(track.id), { credentials: 'include' })
    if (res.ok) {
      await cache.put(streamUrl(track.id), res)
      touch(track.id, track.size)
      await evict(cache, keep)
    }
  } catch { /* network error: playback will just stream */ } finally {
    pending.delete(track.id)
  }
}

async function evict(cache, keep) {
  const meta = readMeta()
  const ids = Object.keys(meta).sort((a, b) => meta[a].t - meta[b].t) // oldest first
  let total = ids.reduce((sum, id) => sum + meta[id].size, 0)
  let count = ids.length
  for (const id of ids) {
    if (count <= MAX_TRACKS && total <= MAX_BYTES) break
    if (keep.has(Number(id))) continue
    await cache.delete(streamUrl(id))
    total -= meta[id].size
    count--
    delete meta[id]
  }
  writeMeta(meta)
}

// ---------- helpers ----------

function readVolume() {
  try {
    const v = parseFloat(localStorage.getItem(VOLUME_KEY))
    return Number.isFinite(v) ? v : 1
  } catch { return 1 }
}

function shuffled(items) {
  const a = [...items]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

// ---------- store ----------

export const usePlayer = defineStore('player', () => {
  const audio = new Audio()
  const base = ref([]) // queue items { uid, track, queued } in original order
  const queue = ref([]) // the same items in play order (shuffled or not)
  const pos = ref(-1) // index of the current item in `queue`
  const source = ref(null) // what is playing: { label, to }
  const shuffle = ref(false)
  const repeat = ref('off') // 'off' | 'all' | 'one'
  const playing = ref(false)
  const time = ref(0)
  const duration = ref(0)
  const volume = ref(readVolume())
  const muted = ref(false)
  let uid = 0
  let loadSeq = 0
  let blobUrl = null

  const current = computed(() => queue.value[pos.value]?.track ?? null)
  const upNext = computed(() => queue.value.slice(pos.value + 1))
  const item = (track, queued = false) => ({ uid: ++uid, track, queued })
  const isPlayingSource = (to) => playing.value && source.value?.to === to

  function upcoming() {
    const n = queue.value.length
    const out = []
    for (let k = 1; k <= PREFETCH_AHEAD && k < n; k++) {
      const p = pos.value + k
      if (p >= n && repeat.value !== 'all') break
      out.push(queue.value[p % n].track)
    }
    return out
  }

  function prefetchUpcoming() {
    const next = upcoming()
    const keep = new Set([current.value?.id, ...next.map((t) => t.id)])
    next.forEach((t) => prefetch(t, keep))
  }

  async function load() {
    const track = current.value
    if (!track) return
    const seq = ++loadSeq
    const cached = await cachedBlobUrl(track.id)
    if (seq !== loadSeq) { // user skipped again while we were reading the cache
      if (cached) URL.revokeObjectURL(cached)
      return
    }
    if (blobUrl) URL.revokeObjectURL(blobUrl)
    blobUrl = cached
    audio.src = cached || streamUrl(track.id)
    await audio.play().catch(() => {})
    setMediaSession(track)
    prefetchUpcoming()
  }

  function playQueue(tracks, start = 0, src = null) {
    if (!tracks.length) return
    base.value = tracks.map((t) => item(t))
    source.value = src
    const first = base.value[start]
    queue.value = shuffle.value ? [first, ...shuffled(base.value.filter((x) => x !== first))] : [...base.value]
    pos.value = shuffle.value ? 0 : start
    load()
  }

  // Play a list that is already loaded (album/playlist page), or pause/resume if it's already playing.
  function playSource(tracks, src) {
    if (source.value?.to === src.to && current.value) return toggle()
    playQueue(tracks, 0, src)
  }

  // Same for a card: fetch the album/artist/playlist first.
  async function playCollection(kind, id) {
    const to = `/${kind}/${id}`
    if (source.value?.to === to && current.value) return toggle()
    const data = await api(`/${ENDPOINT[kind]}/${id}`)
    playQueue(data.tracks, 0, { label: data.title ?? data.name, to })
  }

  // Like Spotify: queued tracks play right after the current one (after earlier queued tracks).
  function addToQueue(track) {
    const it = item(track, true)
    if (!current.value) {
      base.value = [it]
      queue.value = [it]
      pos.value = 0
      source.value = null
      return load()
    }
    let i = pos.value + 1
    while (queue.value[i]?.queued) i++
    queue.value.splice(i, 0, it)
    let j = base.value.indexOf(queue.value[pos.value]) + 1
    while (base.value[j]?.queued) j++
    base.value.splice(j, 0, it)
    prefetchUpcoming()
  }

  function removeAt(i) {
    if (i <= pos.value) return
    const [it] = queue.value.splice(i, 1)
    base.value.splice(base.value.indexOf(it), 1)
    prefetchUpcoming()
  }

  function jumpTo(i) {
    pos.value = i
    load()
  }

  function next() {
    if (pos.value + 1 < queue.value.length) pos.value++
    else if (repeat.value === 'all' && queue.value.length) pos.value = 0
    else return audio.pause()
    load()
  }

  function prev() {
    if (audio.currentTime > 3 || pos.value <= 0) audio.currentTime = 0
    else {
      pos.value--
      load()
    }
  }

  function toggle() {
    if (!current.value) return
    audio.paused ? audio.play() : audio.pause()
  }

  function toggleShuffle() {
    shuffle.value = !shuffle.value
    const cur = queue.value[pos.value]
    if (!cur) return
    queue.value = shuffle.value ? [cur, ...shuffled(queue.value.filter((x) => x !== cur))] : [...base.value]
    pos.value = shuffle.value ? 0 : base.value.indexOf(cur)
    prefetchUpcoming()
  }

  function cycleRepeat() {
    repeat.value = { off: 'all', all: 'one', one: 'off' }[repeat.value]
    prefetchUpcoming()
  }

  const seek = (s) => (audio.currentTime = s)
  const seekBy = (d) => current.value && (audio.currentTime = Math.max(0, Math.min(audio.duration || 0, audio.currentTime + d)))

  const applyVolume = () => (audio.volume = muted.value ? 0 : volume.value)
  function setVolume(v) {
    volume.value = Math.min(1, Math.max(0, v))
    muted.value = false
    applyVolume()
    try { localStorage.setItem(VOLUME_KEY, String(volume.value)) } catch { /* storage unavailable */ }
  }
  function toggleMute() {
    muted.value = !muted.value
    applyVolume()
  }

  // Stop and forget everything (used on logout).
  function reset() {
    loadSeq++ // a track that is still being loaded must not start playing
    audio.pause()
    audio.removeAttribute('src')
    audio.load()
    if (blobUrl) URL.revokeObjectURL(blobUrl)
    blobUrl = null
    base.value = []
    queue.value = []
    pos.value = -1
    source.value = null
    time.value = duration.value = 0
    // The next person at this browser shouldn't find this account's music saved on it.
    if (hasCache) caches.delete(CACHE_NAME).catch(() => {})
    try { localStorage.removeItem(META_KEY) } catch { /* storage unavailable */ }
  }

  function setMediaSession(track) {
    if (!('mediaSession' in navigator)) return
    const cover = trackCoverUrl(track)
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artists.map((a) => a.name).join(', '),
      album: track.album?.title ?? '',
      artwork: cover ? [{ src: cover }] : [],
    })
  }
  if ('mediaSession' in navigator) {
    const ms = navigator.mediaSession
    ms.setActionHandler('play', () => audio.play())
    ms.setActionHandler('pause', () => audio.pause())
    ms.setActionHandler('nexttrack', next)
    ms.setActionHandler('previoustrack', prev)
    ms.setActionHandler('seekto', (e) => seek(e.seekTime))
  }

  applyVolume()
  audio.addEventListener('play', () => (playing.value = true))
  audio.addEventListener('pause', () => (playing.value = false))
  audio.addEventListener('timeupdate', () => (time.value = audio.currentTime))
  audio.addEventListener('loadedmetadata', () => (duration.value = audio.duration))
  // A track that can't be played (deleted from the library meanwhile, server unreachable): say so and move on,
  // instead of looking like it plays. After 3 in a row, stop.
  let failures = 0
  audio.addEventListener('playing', () => (failures = 0))
  audio.addEventListener('error', () => {
    const track = current.value
    if (!track || !audio.getAttribute('src')) return
    useUi().notify(`Can't play “${track.title}”`)
    if (++failures <= 3 && pos.value + 1 < queue.value.length) return next()
    failures = 0
    audio.pause()
    playing.value = false
  })
  audio.addEventListener('ended', () => {
    if (repeat.value === 'one') {
      audio.currentTime = 0
      audio.play()
    } else next()
  })

  return {
    queue, pos, source, shuffle, repeat, playing, time, duration, volume, muted, current, upNext,
    isPlayingSource, playQueue, playSource, playCollection, addToQueue, removeAt, jumpTo,
    next, prev, toggle, toggleShuffle, cycleRepeat, seek, seekBy, setVolume, toggleMute, reset,
  }
})
