<script setup>
import { AudioLines } from 'lucide-vue-next'

defineProps({ title: { type: String, required: true } })
</script>

<template>
  <div class="flex min-h-dvh items-start justify-center bg-linear-to-b from-neutral-800 to-black p-4 text-white md:items-center">
    <div class="w-full max-w-md rounded-xl bg-black/80 px-8 py-10 md:px-12">
      <div class="mb-8 flex flex-col items-center gap-4 text-center">
        <AudioLines class="h-10 w-10 text-accent" />
        <h1 class="text-3xl font-bold tracking-tight">{{ title }}</h1>
      </div>
      <slot />
    </div>
  </div>
</template>

<script>
// Shared classes for the auth forms.
export const input =
  'w-full rounded-md bg-neutral-900 px-3 py-3 ring-1 ring-neutral-500 outline-none transition hover:ring-white focus:ring-2 focus:ring-white'
export const button = 'w-full rounded-full bg-accent py-3 font-bold text-black transition hover:scale-[1.02] disabled:opacity-50'
</script>
