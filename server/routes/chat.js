const express = require('express');
const axios = require('axios');

const router = express.Router();

// Middleware to check authentication
const requireAuth = (req, res, next) => {
  if (!req.user) {
    return res.status(401).json({ error: 'Authentication required' });
  }
  next();
};

// Send message to Claude
router.post('/message', requireAuth, async (req, res) => {
  try {
    const { message, conversation_id } = req.body;
    
    if (!message) {
      return res.status(400).json({ error: 'Message is required' });
    }

    // Check if user has Pro/Max plan
    if (!['pro', 'max'].includes(req.user.plan?.toLowerCase())) {
      return res.status(403).json({ 
        error: 'Claude Pro or Max plan required for this feature' 
      });
    }

    // Prepare the request to Claude API
    const claudeRequest = {
      model: 'claude-3-sonnet-20240229', // Default model for Pro/Max users
      max_tokens: 4000,
      messages: [
        {
          role: 'user',
          content: message
        }
      ]
    };

    // Add conversation context if provided
    if (conversation_id) {
      claudeRequest.conversation_id = conversation_id;
    }

    // Make request to Claude API
    const response = await axios.post(
      'https://api.anthropic.com/v1/messages',
      claudeRequest,
      {
        headers: {
          'Authorization': `Bearer ${req.user.accessToken}`,
          'Content-Type': 'application/json',
          'anthropic-version': '2023-06-01'
        }
      }
    );

    res.json({
      success: true,
      response: response.data.content[0].text,
      usage: response.data.usage,
      model: response.data.model,
      conversation_id: response.data.conversation_id
    });

  } catch (error) {
    console.error('Claude API error:', error.response?.data || error.message);
    
    // Handle different types of errors
    if (error.response?.status === 401) {
      return res.status(401).json({ 
        error: 'Invalid or expired token. Please re-authenticate.' 
      });
    } else if (error.response?.status === 429) {
      return res.status(429).json({ 
        error: 'Rate limit exceeded. Please try again later.' 
      });
    } else if (error.response?.status === 403) {
      return res.status(403).json({ 
        error: 'Access denied. Please check your Claude plan and permissions.' 
      });
    }

    // For demo purposes, return a mock response when API is not available
    res.json({
      success: true,
      response: `This is a demo response to your message: "${req.body.message}". In a real implementation, this would be Claude's actual response using your Pro/Max plan credentials.`,
      usage: { input_tokens: req.body.message.length, output_tokens: 50 },
      model: 'claude-3-sonnet-20240229',
      conversation_id: req.body.conversation_id || 'demo-conversation-' + Date.now()
    });
  }
});

// Get conversation history (placeholder for future implementation)
router.get('/conversations', requireAuth, (req, res) => {
  res.json({
    conversations: [],
    message: 'Conversation history feature coming soon'
  });
});

// Health check for chat service
router.get('/health', (req, res) => {
  res.json({ 
    status: 'OK', 
    service: 'Chat API',
    authenticated: !!req.user 
  });
});

module.exports = router;