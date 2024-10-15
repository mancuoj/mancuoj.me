import React from 'react'
import ReactDOM from 'react-dom/client'
import { Home } from './components/home.tsx'
import '@fontsource-variable/inter'
import '@fontsource-variable/source-serif-4'
import './style.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Home />
  </React.StrictMode>,
)
