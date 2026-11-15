# Frontend plugins

A plugin is a folder here, `src/plugins/<name>/`, with an `index.js`. Every such folder is built into the app;
with none, the app is built as it is. What the `index.js` can export is listed in [`../plugins.js`](../plugins.js).
Plugin code imports the app's own modules with `@/…` (`@` is `src/`), e.g. `import { api } from '@/api'`.

Plugin folders are not part of this repository (git ignores them). They come from their own repository:

- **Local run:** link or copy the folder here, then `npm run dev` as usual.
- **Docker:** the image only takes plugins from the build context named `plugins` (a folder that holds plugin
  folders), never from this folder.
  ```yaml
  build:
    context: ./frontend
    additional_contexts:
      plugins: ../my-plugins/frontend
  ```

A plugin usually has a second half for the API: see `backend/app/plugins/README.md`.
