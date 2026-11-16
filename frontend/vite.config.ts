import { defineConfig } from 'vite';

// Same-origin requests keep the backend local without opening CORS.
const proxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    ws: true,
    rewrite: (path: string) => path.replace(/^\/api/, ''),
  },
};
export default defineConfig({
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
});
