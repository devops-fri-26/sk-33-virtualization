<script setup>
import { Disc3, House, Library, LogOut, Search, Settings, Shield, Upload } from 'lucide-vue-next'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PlayerBar from './components/PlayerBar.vue'
import QueuePanel from './components/QueuePanel.vue'
import Sidebar from './components/Sidebar.vue'
import { pageChanged, nav as pluginNav } from './plugins'
import { useAuth } from './stores/auth'
import { usePlayer } from './stores/player'
import { useUi } from './stores/ui'

const auth = useAuth()
const player = usePlayer()
const ui = useUi()
const route = useRoute()
const router = useRouter()
const main = ref(null)
const userMenu = ref(false)
const mobileNav = computed(() => [
  { to: '/', label: 'Home', icon: House },
  { to: '/search', label: 'Search', icon: Search },
  { to: '/browse', label: 'Browse', icon: Disc3 },
  { to: '/library', label: 'Library', icon: Library },
  { to: '/upload', label: 'Upload', icon: Upload },
  ...pluginNav(),
])

watch(() => route.path, () => main.value?.scrollTo(0, 0))
// Tell the plugins about each page change once logged in (e.g. to re-check that their service is reachable).
watch(() => [route.path, auth.user], () => auth.user && !route.meta.public && pageChanged(), { immediate: true })

function toggleUserMenu() {
  userMenu.value = !userMenu.value
  if (userMenu.value) auth.refresh().catch(() => {}) // fresh admin badge
}

async function logout() {
  userMenu.value = false
  player.reset()
  await auth.logout()
  router.push('/login')
}

// Keyboard shortcuts: Space play/pause, ←/→ seek 5 s, Shift+←/→ previous/next track.
const typing = (e) => e.target.closest?.('input, textarea, select, [contenteditable="true"]')
function onKeydown(e) {
  if (route.meta.public || typing(e) || e.ctrlKey || e.metaKey || e.altKey) return
  const actions = {
    Space: () => player.toggle(),
    ArrowRight: () => (e.shiftKey ? player.next() : player.seekBy(5)),
    ArrowLeft: () => (e.shiftKey ? player.prev() : player.seekBy(-5)),
  }
  if (!actions[e.code]) return
  e.preventDefault()
  actions[e.code]()
}
const onKeyup = (e) => e.code === 'Space' && !typing(e) && e.preventDefault() // don't also "click" a focused button
onMounted(() => {
  addEventListener('keydown', onKeydown)
  addEventListener('keyup', onKeyup)
})
onUnmounted(() => {
  removeEventListener('keydown', onKeydown)
  removeEventListener('keyup', onKeyup)
})
</script>

<template>
  <RouterView v-if="route.meta.public" />
  <div v-else class="flex h-dvh flex-col bg-black text-white md:gap-2 md:p-2">
    <div class="flex min-h-0 flex-1 md:gap-2">
      <Sidebar class="hidden w-72 shrink-0 md:flex" />

      <main ref="main" class="relative min-w-0 flex-1 overflow-y-auto bg-surface md:rounded-lg">
        <div v-if="userMenu" class="fixed inset-0 z-20" @click="userMenu = false" />
        <div class="sticky top-0 z-30 flex h-0 justify-end">
          <div class="relative m-3 h-fit">
            <button class="relative flex h-9 w-9 items-center justify-center rounded-full bg-black/60 p-1 transition hover:scale-105" :title="auth.user?.email" @click="toggleUserMenu">
              <span class="flex h-full w-full items-center justify-center rounded-full bg-accent text-sm font-bold text-black uppercase">{{ (auth.user?.name || auth.user?.email)?.[0] }}</span>
              <span v-if="auth.user?.admin_alerts" class="absolute -top-0.5 -right-0.5 h-3 w-3 rounded-full bg-red-500 ring-2 ring-black" />
            </button>
            <div v-if="userMenu" class="absolute right-0 mt-2 w-60 rounded-md bg-highlight p-1 text-sm shadow-2xl shadow-black/60">
              <div class="px-3 py-2">
                <p v-if="auth.user?.name" class="truncate font-bold">{{ auth.user.name }}</p>
                <p class="truncate text-muted">{{ auth.user?.email }}</p>
              </div>
              <RouterLink to="/settings" class="flex w-full items-center gap-3 rounded-sm px-3 py-2.5 hover:bg-white/10" @click="userMenu = false">
                <Settings class="h-4 w-4" /> Settings
              </RouterLink>
              <RouterLink v-if="auth.user?.is_admin" to="/admin" class="flex w-full items-center gap-3 rounded-sm px-3 py-2.5 hover:bg-white/10" @click="userMenu = false">
                <Shield class="h-4 w-4" /> Admin
                <span v-if="auth.user.admin_alerts" class="ml-auto rounded-full bg-red-500 px-1.5 text-xs leading-5 font-bold">{{ auth.user.admin_alerts }}</span>
              </RouterLink>
              <div class="my-1 border-t border-white/10" />
              <button class="flex w-full items-center gap-3 rounded-sm px-3 py-2.5 hover:bg-white/10" @click="logout"><LogOut class="h-4 w-4" /> Log out</button>
            </div>
          </div>
        </div>
        <RouterView :key="route.path" />
      </main>

      <QueuePanel v-if="ui.queueOpen" />
    </div>

    <PlayerBar />

    <nav class="flex justify-around bg-black px-1 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] text-[11px] md:hidden">
      <RouterLink
        v-for="n in mobileNav"
        :key="n.to"
        :to="n.to"
        class="flex flex-col items-center gap-1 px-2"
        :class="route.path === n.to ? 'text-white' : 'text-muted'"
      >
        <component :is="n.icon" class="h-6 w-6" /> {{ n.label }}
      </RouterLink>
    </nav>

    <Transition enter-from-class="translate-y-2 opacity-0" leave-to-class="opacity-0" enter-active-class="transition" leave-active-class="transition">
      <div v-if="ui.toast" class="pointer-events-none fixed bottom-36 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-black shadow-xl md:bottom-24">
        {{ ui.toast }}
      </div>
    </Transition>
  </div>
</template>
