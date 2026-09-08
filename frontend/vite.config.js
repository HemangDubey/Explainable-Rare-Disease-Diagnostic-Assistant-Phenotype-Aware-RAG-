import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

// Custom plugin to serve landing page at root / and React SPA index.html at all app routes
function landingPagePlugin() {
  return {
    name: 'landing-page',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url.split('?')[0]
        
        // Serve static landing page only at root '/' or '/landing.html'
        if (url === '/' || url === '/landing.html') {
          const landingPath = path.resolve(__dirname, 'public', 'landing.html')
          if (fs.existsSync(landingPath)) {
            res.setHeader('Content-Type', 'text/html')
            res.end(fs.readFileSync(landingPath, 'utf-8'))
            return
          }
        }
        
        // For app routes (/dashboard, /clinical-scribe, /counterfactual, etc.), serve React index.html
        if (!path.extname(url) && !url.startsWith('/api') && !url.startsWith('/@') && !url.startsWith('/node_modules')) {
          const indexPath = path.resolve(__dirname, 'index.html')
          if (fs.existsSync(indexPath)) {
            const html = fs.readFileSync(indexPath, 'utf-8')
            server.transformIndexHtml(req.url, html).then(transformed => {
              res.setHeader('Content-Type', 'text/html')
              res.end(transformed)
            }).catch(next)
            return
          }
        }
        
        next()
      })
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [landingPagePlugin(), react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
