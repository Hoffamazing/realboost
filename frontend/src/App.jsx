import { useState } from 'react'

function App() {
  const [status, setStatus] = useState('Checking backend...')

  // Test the backend connection
  fetch(import.meta.env.VITE_API_URL + '/health')
    .then(res => res.json())
    .then(data => setStatus(`✅ Backend Connected: ${data.service} v${data.version}`))
    .catch(err => setStatus(`❌ Backend Error: ${err.message}`))

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      color: 'white',
      padding: '20px'
    }}>
      <div style={{
        textAlign: 'center',
        maxWidth: '600px'
      }}>
        <h1 style={{ fontSize: '48px', marginBottom: '20px' }}>🏠 REagentAmp AI</h1>
        <p style={{ fontSize: '20px', marginBottom: '40px', opacity: 0.9 }}>
          AI-Powered Real Estate Marketing Platform
        </p>
        <div style={{
          background: 'rgba(255,255,255,0.2)',
          padding: '20px',
          borderRadius: '12px',
          backdropFilter: 'blur(10px)'
        }}>
          <p style={{ fontSize: '18px', margin: 0 }}>{status}</p>
        </div>
        <p style={{ marginTop: '40px', opacity: 0.7, fontSize: '14px' }}>
          Backend: {import.meta.env.VITE_API_URL || 'Not configured'}
        </p>
      </div>
    </div>
  )
}

export default App
