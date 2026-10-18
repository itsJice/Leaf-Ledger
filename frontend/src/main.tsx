import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AppWrapper } from './AppWrapper.tsx'
import './index.css'
import { installPrintSupport } from './utils/printPage'

// Cmd+P prints the whole page you're on (utils/printPage.ts).
installPrintSupport()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppWrapper />
  </StrictMode>,
)
