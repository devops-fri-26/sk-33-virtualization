import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router'

const app = createApp(App).use(createPinia()).use(router)
// Mount once the first page is known. Before that every page looks like a logged-in one, so the login page would
// start by drawing the sidebar, which asks for the playlists without a session.
router.isReady().then(() => app.mount('#app'))
