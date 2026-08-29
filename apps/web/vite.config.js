import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1800,
    // Do not split pdfjs-dist into its own chunk. Forcing a vendor-pdf split
    // made Vite colocate its module-preload helper in that 1.6 MB file, so the
    // entry graph (login + Library) could not run until PDF.js downloaded.
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react-dom/') || id.includes('node_modules/react/') || id.includes('node_modules/react-router')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/lucide-react/')) {
            return 'vendor-icons';
          }
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
  },
  server: {
    allowedHosts: ['qa.fbrcms.edly.io'],
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/uploads': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})
