import { ref, watchEffect } from 'vue'

// Fallback colors ("r g b") for items without a cover, picked by a hash of their name.
const PALETTE = ['80 56 160', '30 80 140', '140 40 70', '40 110 90', '150 90 40', '110 50 120', '30 100 120', '83 83 83']
const hash = (s = '') => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 0) >>> 0

// Spotify-style header color: the average color of the cover (darkened so white text stays readable).
export function useCoverColor(getSrc, getSeed) {
  const color = ref(PALETTE[0])
  watchEffect(() => {
    const src = getSrc()
    color.value = PALETTE[hash(getSeed()) % PALETTE.length]
    if (!src) return
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = canvas.height = 16
      const ctx = canvas.getContext('2d', { willReadFrequently: true })
      ctx.drawImage(img, 0, 0, 16, 16)
      const d = ctx.getImageData(0, 0, 16, 16).data
      const sum = [0, 0, 0]
      for (let i = 0; i < d.length; i += 4) for (let c = 0; c < 3; c++) sum[c] += d[i + c]
      const avg = sum.map((v) => v / (d.length / 4))
      const k = Math.min(1, 150 / Math.max(...avg, 1))
      if (getSrc() === src) color.value = avg.map((v) => Math.round(v * k)).join(' ')
    }
    img.src = src
  })
  return color
}
