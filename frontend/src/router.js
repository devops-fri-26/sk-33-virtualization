import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from './stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/Home.vue') },
    { path: '/search', component: () => import('./views/Search.vue') },
    { path: '/library', component: () => import('./views/Library.vue') },
    { path: '/upload', component: () => import('./views/Upload.vue') },
    { path: '/torrents', component: () => import('./views/Torrents.vue') },
    { path: '/album/:id', component: () => import('./views/Album.vue') },
    { path: '/artist/:id', component: () => import('./views/Artist.vue') },
    { path: '/playlist/:id', component: () => import('./views/Playlist.vue') },
    { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
    { path: '/register', component: () => import('./views/Register.vue'), meta: { public: true } },
    { path: '/verify', component: () => import('./views/Verify.vue'), meta: { public: true } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuth()
  await auth.load()
  if (!to.meta.public && !auth.user) return '/login'
})

export default router
