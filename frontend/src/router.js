import { createRouter, createWebHistory } from 'vue-router'
import { setUnauthorizedHandler } from './api'
import { routes as pluginRoutes } from './plugins'
import { useAuth } from './stores/auth'
import { usePlayer } from './stores/player'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/Home.vue') },
    { path: '/search', component: () => import('./views/Search.vue') },
    { path: '/browse', component: () => import('./views/Browse.vue') },
    { path: '/library', component: () => import('./views/Library.vue') },
    { path: '/upload', component: () => import('./views/Upload.vue') },
    { path: '/album/:id', component: () => import('./views/Album.vue') },
    { path: '/artist/:id', component: () => import('./views/Artist.vue') },
    { path: '/playlist/:id', component: () => import('./views/Playlist.vue') },
    { path: '/settings', component: () => import('./views/Settings.vue') },
    { path: '/admin', component: () => import('./views/Admin.vue'), meta: { admin: true } },
    { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
    { path: '/register', component: () => import('./views/Register.vue'), meta: { public: true } },
    { path: '/verify', component: () => import('./views/Verify.vue'), meta: { public: true } },
    { path: '/forgot-password', component: () => import('./views/ForgotPassword.vue'), meta: { public: true } },
    { path: '/reset-password', component: () => import('./views/ResetPassword.vue'), meta: { public: true } },
    { path: '/confirm-email', component: () => import('./views/ConfirmEmail.vue'), meta: { public: true } },
    ...pluginRoutes,
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuth()
  await auth.load()
  if (!to.meta.public && !auth.user) return '/login'
  if (to.meta.admin && !auth.user.is_admin) return '/'
})

// The session ended while the app was open: go to the login page instead of showing errors on every page.
setUnauthorizedHandler(() => {
  const auth = useAuth()
  if (!auth.user) return
  auth.user = null
  usePlayer().reset()
  router.push('/login')
})

export default router
