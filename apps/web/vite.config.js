import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // Every chunk we author is now well under Vite's 500 kB default; the only one
    // above it is pdfjs-dist's pre-minified worker (~1.17 MB), a single vendored
    // module that cannot be split and is fetched on demand by hooks/pdfjsLoader.js.
    // Raised just past that so the warning still fires on real regressions.
    chunkSizeWarningLimit: 1200,
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
  },
  server: {
    allowedHosts: ['qa.fbrcms.edly.io'],
  },
})
