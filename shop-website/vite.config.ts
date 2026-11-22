import { defineConfig } from 'vite'

export default defineConfig({
  root: 'src',
  publicDir: '../public',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      input: {
        main: 'src/index.html',
        customer: 'src/customer/index.html',
        workshop: 'src/workshop/index.html',
      },
    },
  },
  server: {
    port: 3000,
    open: true,
  },
})