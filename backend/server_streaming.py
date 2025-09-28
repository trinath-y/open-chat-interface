#!/usr/bin/env python3
"""
Real-time Streaming Claude Interface Server
Uses interactive mode with real-time streaming
"""

import os
import sys
import json
import asyncio
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

class StreamingClaudeInterface:
    """Real-time streaming interface with Claude CLI"""

    def __init__(self):
        self.claude_command = os.getenv('CLAUDE_COMMAND', 'claude')
        self.process = None
        self.is_ready = False

    async def start_interactive_session(self):
        """Start an interactive Claude session"""
        # Start Claude in interactive mode (no --print flag!)
        self.process = await asyncio.create_subprocess_exec(
            self.claude_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            bufsize=0  # Unbuffered for real-time
        )

        # Wait for initial prompt
        await self.wait_for_ready()
        self.is_ready = True
        logger.info("Claude interactive session started")

    async def wait_for_ready(self):
        """Wait for Claude to be ready"""
        # Read initial output until we see a prompt
        buffer = ""
        while True:
            try:
                chunk = await asyncio.wait_for(
                    self.process.stdout.read(1024),
                    timeout=0.5
                )
                if chunk:
                    buffer += chunk.decode('utf-8', errors='ignore')
                    # Look for prompt indicators
                    if ">" in buffer or ":" in buffer or len(buffer) > 100:
                        break
            except asyncio.TimeoutError:
                break

    async def send_message_streaming(self, content: str):
        """Send message and stream response in real-time"""
        if not self.is_ready:
            await self.start_interactive_session()

        start_time = time.time()

        # Send the message
        self.process.stdin.write((content + "\n").encode())
        await self.process.stdin.drain()

        # Stream the response
        response_buffer = ""
        last_chunk_time = time.time()

        while True:
            try:
                # Read small chunks for real-time streaming
                chunk = await asyncio.wait_for(
                    self.process.stdout.read(64),  # Small chunks for responsiveness
                    timeout=0.3
                )

                if chunk:
                    text = chunk.decode('utf-8', errors='ignore')
                    response_buffer += text
                    last_chunk_time = time.time()

                    # Yield each chunk immediately
                    yield {
                        'type': 'chunk',
                        'content': text,
                        'timestamp': time.time() - start_time
                    }

                    # Check if response seems complete (basic heuristic)
                    if text.endswith('\n\n') or text.endswith('.\n'):
                        await asyncio.sleep(0.2)  # Brief pause to check for more

            except asyncio.TimeoutError:
                # If no data for 0.3 seconds, check if we should stop
                if time.time() - last_chunk_time > 1.0:  # 1 second of silence
                    break

        # Final event
        yield {
            'type': 'complete',
            'total_time': time.time() - start_time,
            'content': response_buffer
        }

    async def cleanup(self):
        """Clean up the process"""
        if self.process:
            self.process.terminate()
            await self.process.wait()

class StreamingChatServer:
    """Real-time streaming web server"""

    def __init__(self, port=3000):
        self.port = port
        self.sessions = {}  # sid -> StreamingClaudeInterface

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
            # Create a dedicated Claude session for this client
            self.sessions[sid] = StreamingClaudeInterface()

            await self.sio.emit('connected', {
                'status': 'connected',
                'mode': 'Real-time Streaming'
            }, to=sid)

        @self.sio.event
        async def disconnect(sid):
            logger.info(f"Client disconnected: {sid}")
            # Clean up Claude session
            if sid in self.sessions:
                await self.sessions[sid].cleanup()
                del self.sessions[sid]

        @self.sio.event
        async def create_session(sid, data):
            """Create a new chat session"""
            await self.sio.emit('session_created', {
                'session': {
                    'id': f"stream_{uuid.uuid4().hex[:8]}",
                    'created_at': datetime.now().isoformat()
                }
            }, to=sid)

        @self.sio.event
        async def send_message(sid, data):
            """Handle incoming message with real-time streaming"""
            try:
                content = data.get('content', '').strip()
                if not content:
                    raise ValueError("Empty message")

                logger.info(f"Message from {sid}: {content[:50]}...")

                # Get or create Claude interface for this session
                if sid not in self.sessions:
                    self.sessions[sid] = StreamingClaudeInterface()

                claude = self.sessions[sid]

                # Start streaming
                await self.sio.emit('stream_start', {}, to=sid)

                # Send start event
                message_id = f"msg_{uuid.uuid4().hex[:8]}"
                await self.sio.emit('stream_event', {
                    'type': 'message.start',
                    'data': {'id': message_id}
                }, to=sid)

                # Stream the response
                first_chunk = True
                async for event in claude.send_message_streaming(content):
                    if event['type'] == 'chunk':
                        # Send each chunk immediately
                        await self.sio.emit('stream_event', {
                            'type': 'message.delta',
                            'data': {'content': event['content']}
                        }, to=sid)

                        if first_chunk:
                            logger.info(f"First chunk in {event['timestamp']:.2f}s")
                            first_chunk = False

                    elif event['type'] == 'complete':
                        # Send complete event
                        await self.sio.emit('stream_event', {
                            'type': 'message.complete',
                            'data': {
                                'response_time': event['total_time']
                            }
                        }, to=sid)

                        logger.info(f"Response completed in {event['total_time']:.2f}s")

                # End streaming
                await self.sio.emit('stream_end', {}, to=sid)

            except Exception as e:
                logger.error(f"Error handling message: {e}")
                await self.sio.emit('error', {
                    'message': str(e)
                }, to=sid)
                await self.sio.emit('stream_end', {}, to=sid)

    async def index_handler(self, request):
        """Serve the index.html"""
        html_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'index.html')
        if os.path.exists(html_path):
            return web.FileResponse(html_path)
        else:
            return web.Response(text="index.html not found", status=404)

    async def health_handler(self, request):
        """Health check"""
        return web.json_response({
            'status': 'healthy',
            'mode': 'Real-time Streaming Mode',
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
║     Claude Direct Interface - REAL-TIME STREAMING      ║
╠════════════════════════════════════════════════════════╣
║                                                        ║
║  🌐 URL:  http://localhost:{self.port:<5}                        ║
║  ⚡ Mode: Real-time streaming (Interactive)           ║
║  🚀 First byte: <1 second                             ║
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
    server = StreamingChatServer(port=port)

    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\n✅ Server stopped")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()