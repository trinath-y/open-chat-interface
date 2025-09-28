import React from 'react';

const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:3001';

const AuthButton: React.FC = () => {
  const handleLogin = () => {
    window.location.href = `${API_BASE}/auth/claude`;
  };

  return (
    <button 
      onClick={handleLogin}
      className="auth-button"
      style={{
        backgroundColor: '#FF6B35',
        color: 'white',
        border: 'none',
        padding: '12px 24px',
        borderRadius: '8px',
        fontSize: '16px',
        fontWeight: 'bold',
        cursor: 'pointer',
        transition: 'background-color 0.2s'
      }}
      onMouseOver={(e) => {
        e.currentTarget.style.backgroundColor = '#E55A2B';
      }}
      onMouseOut={(e) => {
        e.currentTarget.style.backgroundColor = '#FF6B35';
      }}
    >
      Connect with Claude Pro/Max
    </button>
  );
};

export default AuthButton;