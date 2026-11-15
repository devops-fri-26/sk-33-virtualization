import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }, // plugins import app code as '@/api'
    preserveSymlinks: true, // a plugin folder linked into src/plugins/ behaves like a real folder there
  },
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
