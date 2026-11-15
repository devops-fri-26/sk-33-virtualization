// Plugins: optional features in their own folder, src/plugins/<name>/ (see src/plugins/README.md).
// Each folder's index.js default-exports an object. Every field is optional:
//   routes          pages (vue-router routes), added to the app's own
//   nav()           items for the sidebar and the phone menu: [{ to, label, icon }]
//   searchSections  components shown under the search results; they get the search text as prop `q`
//   pageChanged()   called on every page change while logged in
const plugins = Object.values(import.meta.glob('./plugins/*/index.js', { eager: true })).map((m) => m.default)

export const routes = plugins.flatMap((p) => p.routes ?? [])
export const searchSections = plugins.flatMap((p) => p.searchSections ?? [])
export const nav = () => plugins.flatMap((p) => p.nav?.() ?? []) // call it inside a computed: items can come and go
export const pageChanged = () => plugins.forEach((p) => p.pageChanged?.())
