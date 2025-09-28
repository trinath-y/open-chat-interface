#!/usr/bin/env python3
"""
Working Claude Interface Server using Claude CLI --print mode
This mirrors how OpenCode would work but uses your Claude CLI authentication
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
    """Interface with Claude CLI using --print mode"""

    def __init__(self):
        self.claude_command = os.getenv('CLAUDE_COMMAND', 'claude')

    async def send_message(self, content: str, session_id: str = None) -> Dict[str, Any]:
        """Send a message to Claude and get response"""

        # Build command
        cmd = [
            self.claude_command,
            '--print',  # Non-interactive mode
            '--output-format', 'json'  # Get structured output
        ]

        # If we have a session, continue it
        if session_id:
            cmd.extend(['--resume', session_id])

        # Add the message
        cmd.append(content)

        logger.info(f"Running command: {' '.join(cmd[:5])}...")

        # Run Claude CLI
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Claude CLI error: {stderr.decode()}")
                raise Exception(f"Claude CLI failed: {stderr.decode()}")

            # Parse JSON response
            response = json.loads(stdout.decode())

            return {
                "content": response.get("result", ""),
                "session_id": response.get("session_id"),
                "usage": response.get("usage", {}),
                "cost": response.get("total_cost_usd", 0)
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response: {e}")
            # Fallback to plain text mode
            return await self.send_message_plain(content)
        except Exception as e:
            logger.error(f"Failed to call Claude: {e}")
            raise

    async def send_message_plain(self, content: str) -> Dict[str, Any]:
        """Send message in plain text mode as fallback"""
        cmd = [self.claude_command, '--print', content]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"Claude CLI failed: {stderr.decode()}")

        return {
            "content": stdout.decode().strip(),
            "session_id": None,
            "usage": {},
            "cost": 0
        }

class ChatServer:
    """Web server for Claude chat interface"""

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
                'mode': 'Claude CLI'
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
                'message_count': 0
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

                # Start streaming
                await self.sio.emit('stream_start', {}, to=sid)

                # Send to Claude
                logger.info(f"Sending to Claude: {content[:100]}...")
                response = await self.claude.send_message(
                    content,
                    session_id=session['claude_session_id']
                )

                # Update session
                if response['session_id']:
                    session['claude_session_id'] = response['session_id']
                session['message_count'] += 1

                # Stream response character by character for effect
                response_text = response['content']

                # Send start event
                await self.sio.emit('stream_event', {
                    'type': 'message.start',
                    'data': {'id': f"msg_{uuid.uuid4().hex[:8]}"}
                }, to=sid)

                # Stream characters
                chunk_size = 5  # Send 5 characters at a time for smoother streaming
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i+chunk_size]
                    await self.sio.emit('stream_event', {
                        'type': 'message.delta',
                        'data': {'content': chunk}
                    }, to=sid)
                    await asyncio.sleep(0.01)  # Small delay for streaming effect

                # Send complete event
                await self.sio.emit('stream_event', {
                    'type': 'message.complete',
                    'data': {
                        'usage': response.get('usage', {}),
                        'cost': response.get('cost', 0)
                    }
                }, to=sid)

                # End streaming
                await self.sio.emit('stream_end', {}, to=sid)

                logger.info("Response sent successfully")

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
            'mode': 'Claude CLI --print',
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
║         Claude Direct Interface - Working Server       ║
╠════════════════════════════════════════════════════════╣
║                                                        ║
║  🌐 URL:  http://localhost:{self.port:<5}                        ║
║  🔧 Mode: Claude CLI (using your authentication)      ║
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