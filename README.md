# Open Chat Interface

A modern web-based chat interface that allows you to use your Claude Pro or Max plan through OAuth authentication. Built with React and Node.js.

## Features

- 🔐 **OAuth Authentication**: Secure authentication with your Claude Pro/Max account
- 💬 **Real-time Chat**: Clean, responsive chat interface
- 🚀 **Modern Stack**: React + TypeScript frontend, Node.js + Express backend
- 📱 **Responsive Design**: Works great on desktop and mobile
- ⚡ **Fast & Reliable**: Optimized for performance and user experience

## Prerequisites

- Node.js 16+ and npm
- Claude Pro or Max account
- Claude OAuth application credentials

## Setup Instructions

### 1. Clone and Install Dependencies

```bash
git clone <repository-url>
cd open-chat-interface
npm run install-deps
```

### 2. Configure Environment Variables

Copy the example environment file and configure your OAuth credentials:

```bash
cp .env.example .env
```

Edit `.env` and add your Claude OAuth credentials:

```env
CLAUDE_CLIENT_ID=your_claude_client_id_here
CLAUDE_CLIENT_SECRET=your_claude_client_secret_here
CLAUDE_REDIRECT_URI=http://localhost:3001/auth/claude/callback
SESSION_SECRET=your_session_secret_here
```

### 3. Run the Application

For development (runs both frontend and backend):
```bash
npm run dev
```

Or run separately:
```bash
# Backend (port 3001)
npm run server

# Frontend (port 3000)
npm run client
```

### 4. Access the Application

Open your browser and navigate to:
- Frontend: http://localhost:3000
- Backend API: http://localhost:3001

## OAuth Setup

To use this application, you'll need to register an OAuth application with Anthropic:

1. Go to the Anthropic Developer Console
2. Create a new OAuth application
3. Set the redirect URI to: `http://localhost:3001/auth/claude/callback`
4. Copy the Client ID and Client Secret to your `.env` file

## Usage

1. Open the application in your browser
2. Click "Connect with Claude Pro/Max" to authenticate
3. Grant permissions to the application
4. Start chatting with Claude using your Pro/Max plan!

## Project Structure

```
open-chat-interface/
├── client/                 # React frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── types.ts        # TypeScript types
│   │   └── App.tsx         # Main App component
│   └── public/             # Static files
├── server/                 # Express backend
│   ├── routes/             # API routes
│   │   ├── auth.js         # OAuth authentication
│   │   └── chat.js         # Chat API endpoints
│   └── index.js            # Server entry point
├── .env.example            # Environment variables template
└── package.json            # Project dependencies
```

## API Endpoints

### Authentication
- `GET /auth/claude` - Initiate OAuth flow
- `GET /auth/claude/callback` - OAuth callback
- `GET /auth/user` - Get current user info
- `POST /auth/logout` - Logout user

### Chat
- `POST /api/chat/message` - Send message to Claude
- `GET /api/chat/conversations` - Get conversation history (coming soon)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Support

If you encounter any issues or have questions, please open an issue on GitHub.
