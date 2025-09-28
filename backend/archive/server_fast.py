#!/usr/bin/env python3
"""
Fast Claude Interface Server - optimized for speed
Uses plain text mode for faster responses
"""

import os
import sys
import json
import asyncio
import subprocess
import time
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from aiohttp import web
import socketio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ClaudeInterface:
    """Fast interface with Claude CLI using plain text mode"""

    def __init__(self):
        self.claude_command = os.getenv('CLAUDE_COMMAND', 'claude')
        self.sessions = {}  # Track sessions manually

    async def send_message(self, content: str, session_id: str = None) -> Dict[str, Any]:
        """Send a message to Claude and get response - FAST VERSION"""

        # Build command - NO JSON FORMAT for speed
        cmd = [
            self.claude_command,
            '--print'  # Just plain text mode
        ]

        # Add the message
        cmd.append(content)

        start_time = time.time()
        logger.info(f"Sending to Claude (fast mode): {content[:50]}...")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            elapsed = time.time() - start_time
            logger.info(f"Claude responded in {elapsed:.2f} seconds")

            if process.returncode != 0:
                logger.error(f"Claude CLI error: {stderr.decode()}")
                raise Exception(f"Claude CLI failed: {stderr.decode()}")

            # Return plain text response
            return {
                "content": stdout.decode().strip(),
                "session_id": session_id or str(uuid.uuid4())[:8],
                "usage": {},
                "cost": 0,
                "response_time": elapsed
            }

        except Exception as e:
            logger.error(f"Failed to call Claude: {e}")
            raise

class ChatServer:
    """Fast web server for Claude chat interface"""

    def __init__(self, port=3000):
        self.port = port
        self.claude = ClaudeInterface()
        self.sessions = {}

        # Setup SocketIO
        self.sio = socketio.AsyncServer(
            cors_allowed_origins="*",
            async_mode='aiohttp'
        )
        self.app = web.Application()
        self.sio.attach(self.app)

        self.setup_routes()
        self.setup_socketio()

    def setup_routes(self):
        """Setup HTTP routes"""
        self.app.router.add_get('/', self.index_handler)
        self.app.router.add_get('/health', self.health_handler)

    def setup_socketio(self):
        """Setup SocketIO handlers"""

        @self.sio.event
        async def connect(sid, environ):
            logger.info(f"Client connected: {sid}")
            await self.sio.emit('connected', {
                'status': 'connected',
                'mode': 'Claude CLI (Fast Mode)'
            }, to=sid)

        @self.sio.event
        async def disconnect(sid):
            logger.info(f"Client disconnected: {sid}")
            if sid in self.sessions:
                del self.sessions[sid]

        @self.sio.event
        async def create_session(sid, data):
            """Create a new chat session"""
            self.sessions[sid] = {
                'id': f"session_{uuid.uuid4().hex[:8]}",
                'claude_session_id': None,
                'created_at': datetime.now().isoformat(),
                'message_count': 0,
                'messages': []  # Store message history
            }

            await self.sio.emit('session_created', {
                'session': self.sessions[sid]
            }, to=sid)

            logger.info(f"Created session for {sid}")

        @self.sio.event
        async def send_message(sid, data):
            """Handle incoming message"""
            try:
                content = data.get('content', '').strip()
                if not content:
                    raise ValueError("Empty message")

                # Get or create session
                if sid not in self.sessions:
                    await create_session(sid, {})

                session = self.sessions[sid]

                # Add context from previous messages (simple approach)
                context = ""
                if session['messages']:
                    # Include last 2 exchanges for context
                    recent = session['messages'][-4:] if len(session['messages']) >= 4 else session['messages']
                    for msg in recent:
                        context += f"{msg['role']}: {msg['content'][:200]}\n"
                    context += f"\nUser: {content}\nAssistant:"
                    full_prompt = context
                else:
                    full_prompt = content

                # Start streaming
                await self.sio.emit('stream_start', {}, to=sid)

                # Send to Claude (fast mode)
                response = await self.claude.send_message(
                    full_prompt,
                    session_id=session['claude_session_id']
                )

                # Store messages
                session['messages'].append({'role': 'user', 'content': content})
                session['messages'].append({'role': 'assistant', 'content': response['content']})
                session['message_count'] += 1

                # Stream response character by character for effect
                response_text = response['content']

                # Send start event
                await self.sio.emit('stream_event', {
                    'type': 'message.start',
                    'data': {'id': f"msg_{uuid.uuid4().hex[:8]}"}
                }, to=sid)

                # Stream characters (faster chunks for quick response)
                chunk_size = 20  # Larger chunks for faster streaming
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i+chunk_size]
                    await self.sio.emit('stream_event', {
                        'type': 'message.delta',
                        'data': {'content': chunk}
                    }, to=sid)
                    await asyncio.sleep(0.005)  # Shorter delay

                # Send complete event
                await self.sio.emit('stream_event', {
                    'type': 'message.complete',
                    'data': {
                        'usage': response.get('usage', {}),
                        'cost': response.get('cost', 0),
                        'response_time': response.get('response_time', 0)
                    }
                }, to=sid)

                # End streaming
                await self.sio.emit('stream_end', {}, to=sid)

                logger.info(f"Response sent successfully in {response.get('response_time', 0):.2f}s")

            except Exception as e:
                logger.error(f"Error handling message: {e}")
                await self.sio.emit('error', {
                    'message': str(e)
                }, to=sid)
                await self.sio.emit('stream_end', {}, to=sid)

    async def index_handler(self, request):
        """Serve the index.html"""
        # Look for index.html in the frontend folder
        html_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'index.html')
        if os.path.exists(html_path):
            return web.FileResponse(html_path)
        else:
            return web.Response(text="index.html not found", status=404)

    async def health_handler(self, request):
        """Health check"""
        # Test Claude CLI
        try:
            result = subprocess.run(
                [self.claude.claude_command, '--version'],
                capture_output=True,
                timeout=5
            )
            claude_available = result.returncode == 0
        except:
            claude_available = False

        return web.json_response({
            'status': 'healthy' if claude_available else 'degraded',
            'claude_cli': 'available' if claude_available else 'not found',
            'mode': 'Claude CLI Fast Mode (Plain Text)',
            'timestamp': datetime.now().isoformat()
        })

    async def run(self):
        """Run the server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()

        print(f"""
╔════════════════════════════════════════════════════════╗
║       Claude Direct Interface - FAST MODE              ║
╠════════════════════════════════════════════════════════╣
║                                                        ║
║  🌐 URL:  http://localhost:{self.port:<5}                        ║
║  ⚡ Mode: Fast Plain Text (No JSON overhead)          ║
║                                                        ║
║  ✅ Server is running! Open the URL in your browser.   ║
║                                                        ║
║  Press Ctrl+C to stop                                 ║
╚════════════════════════════════════════════════════════╝
""")

        # Keep running
        await asyncio.Event().wait()

def main():
    """Main entry point"""
    port = int(os.getenv('WEB_PORT', '3000'))
    server = ChatServer(port=port)

    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\n✅ Server stopped")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()