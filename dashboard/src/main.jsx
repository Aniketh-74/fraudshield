import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'leaflet/dist/leaflet.css'
import './index.css'
import App from './App.jsx'

// Fix Leaflet default icon broken image issue under Vite bundler
// Must be done before any react-leaflet component renders
import L from 'leaflet'
delete L.Icon.Default.prototype._getIconUrl

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
