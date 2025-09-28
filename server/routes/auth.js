const express = require('express');
const passport = require('passport');
const OAuth2Strategy = require('passport-oauth2');
const axios = require('axios');

const router = express.Router();

// Check if OAuth credentials are configured
const hasOAuthCredentials = process.env.CLAUDE_CLIENT_ID && 
                           process.env.CLAUDE_CLIENT_SECRET && 
                           process.env.CLAUDE_CLIENT_ID !== 'demo_client_id';

if (hasOAuthCredentials) {
  // Configure Claude OAuth2 Strategy only if credentials are available
  passport.use('claude', new OAuth2Strategy({
    authorizationURL: 'https://api.anthropic.com/oauth/authorize',
    tokenURL: 'https://api.anthropic.com/oauth/token',
    clientID: process.env.CLAUDE_CLIENT_ID,
    clientSecret: process.env.CLAUDE_CLIENT_SECRET,
    callbackURL: process.env.CLAUDE_REDIRECT_URI || 'http://localhost:3001/auth/claude/callback'
  }, async (accessToken, refreshToken, profile, done) => {
    try {
      // Get user info from Claude API
      const response = await axios.get('https://api.anthropic.com/v1/user', {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        }
      });
      
      const user = {
        id: response.data.id || 'claude-user',
        email: response.data.email,
        plan: response.data.plan || 'pro',
        accessToken,
        refreshToken
      };
      
      return done(null, user);
    } catch (error) {
      console.error('OAuth profile fetch error:', error.response?.data || error.message);
      // For demo purposes, create a mock user when API is not available
      const mockUser = {
        id: 'demo-user',
        email: 'demo@example.com',
        plan: 'pro',
        accessToken,
        refreshToken
      };
      return done(null, mockUser);
    }
  }));
} else {
  console.warn('⚠️  OAuth credentials not configured. Using demo mode.');
}

// Serialize/deserialize user for session
passport.serializeUser((user, done) => {
  done(null, user);
});

passport.deserializeUser((user, done) => {
  done(null, user);
});

// Auth routes
router.get('/claude', (req, res) => {
  if (!hasOAuthCredentials) {
    // Demo mode - simulate successful authentication
    const demoUser = {
      id: 'demo-user-' + Date.now(),
      email: 'demo@example.com',
      plan: 'pro',
      accessToken: 'demo_access_token',
      refreshToken: 'demo_refresh_token'
    };
    
    // Store demo user in session
    req.session.demoUser = demoUser;
    
    req.login(demoUser, (err) => {
      if (err) {
        return res.redirect(`${process.env.CLIENT_URL || 'http://localhost:3000'}?auth=failure`);
      }
      res.redirect(`${process.env.CLIENT_URL || 'http://localhost:3000'}?auth=success`);
    });
  } else {
    passport.authenticate('claude', {
      scope: ['read', 'write']
    })(req, res);
  }
});

router.get('/claude/callback', (req, res) => {
  if (!hasOAuthCredentials) {
    return res.redirect(`${process.env.CLIENT_URL || 'http://localhost:3000'}?auth=failure`);
  }
  
  passport.authenticate('claude', { failureRedirect: '/auth/failure' })(req, res, () => {
    // Successful authentication
    res.redirect(`${process.env.CLIENT_URL || 'http://localhost:3000'}?auth=success`);
  });
});

router.get('/failure', (req, res) => {
  res.redirect(`${process.env.CLIENT_URL || 'http://localhost:3000'}?auth=failure`);
});

router.get('/user', (req, res) => {
  if (req.user || req.session.demoUser) {
    const user = req.user || req.session.demoUser;
    res.json({
      authenticated: true,
      user: {
        id: user.id,
        email: user.email,
        plan: user.plan
      }
    });
  } else {
    res.json({ authenticated: false });
  }
});

router.post('/logout', (req, res) => {
  req.logout((err) => {
    if (err) {
      return res.status(500).json({ error: 'Logout failed' });
    }
    res.json({ message: 'Logged out successfully' });
  });
});

// Configuration status endpoint
router.get('/config', (req, res) => {
  res.json({
    oauthConfigured: hasOAuthCredentials,
    demoMode: !hasOAuthCredentials
  });
});

module.exports = router;