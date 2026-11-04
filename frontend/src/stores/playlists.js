import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

// The user's playlists (names + counts), shared by the sidebar, library and "add to playlist" menus.
export const usePlaylists = defineStore('playlists', () => {
  const list = ref([])
  const load = async () => (list.value = await api('/playlists'))

  async function create(name) {
    const pl = await api('/playlists', { method: 'POST', body: { name } })
    await load()
    return pl
  }
  const createNext = () => create(`My Playlist #${list.value.length + 1}`)

  async function addTrack(playlistId, trackId) {
    await api(`/playlists/${playlistId}/tracks`, { method: 'POST', body: { track_id: trackId } })
    await load()
  }
  return { list, load, create, createNext, addTrack }
})
