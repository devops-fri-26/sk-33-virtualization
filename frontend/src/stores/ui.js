import { defineStore } from 'pinia'
import { ref } from 'vue'

// UI-only state: queue panel visibility and short toast messages.
export const useUi = defineStore('ui', () => {
  const queueOpen = ref(false)
  const toast = ref('')
  let timer
  function notify(message) {
    toast.value = message
    clearTimeout(timer)
    timer = setTimeout(() => (toast.value = ''), 2500)
  }
  return { queueOpen, toast, notify }
})
