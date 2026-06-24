import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { siteSeoPlugin } from './plugins/vite-plugin-site-seo'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), siteSeoPlugin()],
})
