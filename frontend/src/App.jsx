import { useState, useEffect } from 'react'
import Login from './Login'
import Signup from './Signup'

function Dashboard({ agent, onLogout }) {
  return (
    <div style={{
      minHeight: '100vh',
      background: '#f7fafc',
      fontFamily: 'system-ui, -apple-system, sans-serif'
    }}>
      {/* Header */}
      <div style={{
        background: 'white',
        borderBottom: '1px solid #e2e8f0',
        padding: '16px 24px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 'bold', color: '#1a202c', margin: 0 }}>
            🚀 REagentAmp
          </h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '14px', fontWeight: '600', color: '#2d3748' }}>
              {agent.full_name}
            </div>
            <div style={{ fontSize: '12px', color: '#718096' }}>
              {agent.subscription_plan} • {agent.subscription_status}
            </div>
          </div>
          <button
            onClick={onLogout}
            style={{
              background: '#e53e3e',
              color: 'white',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '8px',
              fontSize: '14px',
              fontWeight: '600',
              cursor: 'pointer'
            }}
          >
            Logout
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div style={{ padding: '40px 24px', maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          borderRadius: '20px',
          padding: '60px 40px',
          textAlign: 'center',
          color: 'white',
          marginBottom: '40px'
        }}>
          <h2 style={{ fontSize: '48px', margin: '0 0 16px 0' }}>
            Welcome to REagentAmp! 🎉
          </h2>
          <p style={{ fontSize: '20px', opacity: 0.9, margin: 0 }}>
            Your enterprise real estate marketing platform is ready
          </p>
        </div>

        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', 
          gap: '24px' 
        }}>
          {[
            { title: 'AI Lead Qualification', icon: '🤖', desc: 'GPT-4o powered lead scoring and conversations' },
            { title: 'Multi-Platform Ads', icon: '📢', desc: 'Meta, Google, TikTok, Waze integration ready' },
            { title: 'Hot Lead Alerts', icon: '🔥', desc: 'Instant SMS and email notifications' },
            { title: 'Drip Campaigns', icon: '📧', desc: 'Automated email sequences' },
            { title: 'Team Management', icon: '👥', desc: 'Multi-agent dashboard and routing' },
            { title: 'Elite Coaching', icon: '🎯', desc: 'Access to Danny Diaz & Justin Michael' }
          ].map(feature => (
            <div key={feature.title} style={{
              background: 'white',
              padding: '32px',
              borderRadius: '16px',
              border: '1px solid #e2e8f0',
              textAlign: 'center'
            }}>
              <div style={{ fontSize: '48px', marginBottom: '16px' }}>{feature.icon}</div>
              <h3 style={{ 
                fontSize: '18px', 
                fontWeight: 'bold', 
                color: '#1a202c', 
                margin: '0 0 8px 0' 
              }}>
                {feature.title}
              </h3>
              <p style={{ fontSize: '14px', color: '#718096', margin: 0 }}>
                {feature.desc}
              </p>
            </div>
          ))}
        </div>

        <div style={{
          marginTop: '40px',
          background: 'white',
          padding: '32px',
          borderRadius: '16px',
          border: '1px solid #e2e8f0'
        }}>
          <h3 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '16px' }}>
            🚀 Next Steps
          </h3>
          <ul style={{ lineHeight: '2', color: '#4a5568' }}>
            <li>Connect your ad accounts (Meta, Google, TikTok, Waze)</li>
            <li>Set up your first drip campaign</li>
            <li>Configure hot lead alert preferences</li>
            <li>Import existing leads or wait for ad platform integration</li>
            <li>Upgrade to unlock team features and elite coaching</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

function App() {
  const [currentView, setCurrentView] = useState('loading')
  const [agent, setAgent] = useState(null)

  useEffect(() => {
    // Check for stored auth token on load
    const token = localStorage.getItem('reagentamp_token')
    const storedAgent = localStorage.getItem('reagentamp_agent')

    if (token && storedAgent) {
      setAgent(JSON.parse(storedAgent))
      setCurrentView('dashboard')
    } else {
      // Check URL path
      const path = window.location.pathname
      if (path === '/signup') {
        setCurrentView('signup')
      } else {
        setCurrentView('login')
      }
    }
  }, [])

  const handleLogin = (agentData) => {
    setAgent(agentData)
    setCurrentView('dashboard')
    window.history.pushState({}, '', '/')
  }

  const handleSignup = (agentData) => {
    setAgent(agentData)
    setCurrentView('dashboard')
    window.history.pushState({}, '', '/')
  }

  const handleLogout = () => {
    localStorage.removeItem('reagentamp_token')
    localStorage.removeItem('reagentamp_agent')
    setAgent(null)
    setCurrentView('login')
    window.history.pushState({}, '', '/login')
  }

  // Handle browser back/forward
  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname
      if (path === '/signup') {
        setCurrentView('signup')
      } else if (path === '/login') {
        setCurrentView('login')
      }
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  if (currentView === 'loading') {
    return <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      color: 'white',
      fontSize: '24px'
    }}>
      Loading...
    </div>
  }

  if (currentView === 'login') {
    return <Login onLogin={handleLogin} />
  }

  if (currentView === 'signup') {
    return <Signup onSignup={handleSignup} />
  }

  return <Dashboard agent={agent} onLogout={handleLogout} />
}

export default App
