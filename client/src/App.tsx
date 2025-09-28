import React, { useState, useEffect } from 'react';
import './App.css';
import ChatInterface from './components/ChatInterface';
import AuthButton from './components/AuthButton';
import { User, AuthStatus } from './types';

const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:3001';

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authStatus, setAuthStatus] = useState<AuthStatus>('loading');

  useEffect(() => {
    checkAuthStatus();
    
    // Check for auth callback
    const urlParams = new URLSearchParams(window.location.search);
    const authResult = urlParams.get('auth');
    
    if (authResult === 'success') {
      setAuthStatus('success');
      // Remove auth parameter from URL
      window.history.replaceState({}, document.title, window.location.pathname);
      checkAuthStatus();
    } else if (authResult === 'failure') {
      setAuthStatus('error');
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  const checkAuthStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/user`, {
        credentials: 'include'
      });
      const data = await response.json();
      
      if (data.authenticated) {
        setUser(data.user);
        setAuthStatus('authenticated');
      } else {
        setUser(null);
        setAuthStatus('unauthenticated');
      }
    } catch (error) {
      console.error('Auth check failed:', error);
      setAuthStatus('error');
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        credentials: 'include'
      });
      setUser(null);
      setAuthStatus('unauthenticated');
    } catch (error) {
      console.error('Logout failed:', error);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Claude Chat Interface</h1>
        {user && (
          <div className="user-info">
            <span>Welcome, {user.email} ({user.plan} plan)</span>
            <button onClick={handleLogout} className="logout-btn">
              Logout
            </button>
          </div>
        )}
      </header>

      <main className="App-main">
        {authStatus === 'loading' && (
          <div className="loading">Loading...</div>
        )}
        
        {authStatus === 'unauthenticated' && (
          <div className="auth-container">
            <h2>Welcome to Claude Chat Interface</h2>
            <p>Connect your Claude Pro or Max account to start chatting.</p>
            <AuthButton />
          </div>
        )}

        {authStatus === 'authenticated' && user && (
          <ChatInterface user={user} />
        )}

        {authStatus === 'error' && (
          <div className="error-container">
            <h2>Authentication Error</h2>
            <p>There was an issue with authentication. Please try again.</p>
            <AuthButton />
          </div>
        )}

        {authStatus === 'success' && (
          <div className="success-container">
            <h2>Authentication Successful!</h2>
            <p>Redirecting...</p>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
