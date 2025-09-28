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
    """Real-time streaming interface with Claude CLI using stream-json format"""

    def __init__(self):
        self.claude_command = os.getenv('CLAUDE_COMMAND', 'claude')
        self.process = None
        self.current_tools = {}  # Track active tools
        self.session_id = None

    async def send_message_streaming(self, content: str):
        """Send message using stream-json format for real-time streaming"""
        start_time = time.time()

        # Build Claude command with required streaming flags (verbose is required for stream-json)
        cmd = [
            self.claude_command,
            '--output-format', 'stream-json',
            '--include-partial-messages',
            '--verbose',
            content
        ]

        logger.info(f"Starting Claude with stream-json: {' '.join(cmd[:3])}...")

        # Start the process
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            bufsize=0  # Unbuffered for real-time
        )

        # Process the stream
        buffer = ""
        first_content = True

        try:
            while True:
                # Read larger chunks for better performance
                chunk = await asyncio.wait_for(
                    self.process.stdout.read(8192),
                    timeout=30.0  # 30 second timeout
                )

                if not chunk:
                    break

                buffer += chunk.decode('utf-8', errors='ignore')

                # Process complete lines
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        try:
                            event_data = json.loads(line.strip())

                            # Process the event
                            async for result in self._process_event(event_data, start_time, first_content):
                                yield result
                                if result.get('type') == 'content_delta':
                                    first_content = False

                        except json.JSONDecodeError:
                            # Skip invalid JSON lines
                            continue

        except asyncio.TimeoutError:
            logger.warning("Claude process timed out")
        except Exception as e:
            logger.error(f"Error processing Claude stream: {e}")
            yield {
                'type': 'error',
                'content': str(e),
                'timestamp': time.time() - start_time
            }
        finally:
            # Cleanup - suppress errors during normal termination
            if self.process:
                try:
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    # Only log if process won't terminate gracefully
                    logger.warning("Claude process didn't terminate gracefully, killing...")
                    self.process.kill()
                except Exception:
                    # Don't log normal cleanup errors
                    pass

        # Final completion event
        yield {
            'type': 'complete',
            'total_time': time.time() - start_time
        }

    async def _process_event(self, event_data: Dict[str, Any], start_time: float, first_content: bool):
        """Process individual stream-json events"""
        event_type = event_data.get('type')
        timestamp = time.time() - start_time

        if event_type == 'system':
            # System initialization
            self.session_id = event_data.get('session_id')
            yield {
                'type': 'system',
                'session_id': self.session_id,
                'tools': event_data.get('tools', []),
                'model': event_data.get('model'),
                'timestamp': timestamp
            }

        elif event_type == 'stream_event':
            # Extract the nested event
            nested_event = event_data.get('event', {})
            nested_type = nested_event.get('type')

            if nested_type == 'message_start':
                message = nested_event.get('message', {})
                yield {
                    'type': 'message_start',
                    'message_id': message.get('id'),
                    'model': message.get('model'),
                    'timestamp': timestamp
                }

            elif nested_type == 'content_block_start':
                content_block = nested_event.get('content_block', {})
                block_type = content_block.get('type')

                if block_type == 'tool_use':
                    tool_id = content_block.get('id')
                    tool_name = content_block.get('name')

                    # Track this tool
                    self.current_tools[tool_id] = {
                        'name': tool_name,
                        'input': {},
                        'partial_input': ''
                    }

                    yield {
                        'type': 'tool_start',
                        'tool_id': tool_id,
                        'tool_name': tool_name,
                        'timestamp': timestamp
                    }

            elif nested_type == 'content_block_delta':
                delta = nested_event.get('delta', {})
                delta_type = delta.get('type')

                if delta_type == 'text_delta':
                    text = delta.get('text', '')
                    yield {
                        'type': 'content_delta',
                        'content': text,
                        'timestamp': timestamp,
                        'first_chunk': first_content
                    }

                elif delta_type == 'input_json_delta':
                    # Tool input being built
                    index = nested_event.get('index', 0)
                    partial_json = delta.get('partial_json', '')

                    # Find the tool being updated
                    for tool_id, tool_info in self.current_tools.items():
                        if index == 1:  # Tool use blocks are typically at index 1
                            tool_info['partial_input'] += partial_json

                            # Try to parse complete input
                            try:
                                if tool_info['partial_input'].endswith('}'):
                                    tool_info['input'] = json.loads(tool_info['partial_input'])
                            except:
                                pass

                            yield {
                                'type': 'tool_input_delta',
                                'tool_id': tool_id,
                                'tool_name': tool_info['name'],
                                'partial_input': tool_info['partial_input'],
                                'complete_input': tool_info.get('input'),
                                'timestamp': timestamp
                            }
                            break

            elif nested_type == 'content_block_stop':
                index = nested_event.get('index', 0)
                if index == 1:  # Tool block completed
                    yield {
                        'type': 'tool_complete',
                        'timestamp': timestamp
                    }

            elif nested_type == 'message_stop':
                yield {
                    'type': 'message_stop',
                    'timestamp': timestamp
                }

        elif event_type == 'user':
            # Tool result
            message = event_data.get('message', {})
            content = message.get('content', [])

            for content_item in content:
                if content_item.get('type') == 'tool_result':
                    tool_use_id = content_item.get('tool_use_id')
                    result_content = content_item.get('content', '')
                    is_error = content_item.get('is_error', False)

                    yield {
                        'type': 'tool_result',
                        'tool_id': tool_use_id,
                        'content': result_content,
                        'is_error': is_error,
                        'timestamp': timestamp
                    }

        elif event_type == 'result':
            # Final result
            yield {
                'type': 'final_result',
                'result': event_data.get('result'),
                'duration_ms': event_data.get('duration_ms'),
                'cost_usd': event_data.get('total_cost_usd'),
                'timestamp': timestamp
            }

    async def cleanup(self):
        """Clean up the process"""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=3.0)
            except Exception:
                # Suppress cleanup errors during session cleanup
                pass

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

                # Stream the response with proper event handling
                first_chunk = True
                current_tool_name = None

                async for event in claude.send_message_streaming(content):
                    event_type = event.get('type')

                    if event_type == 'system':
                        await self.sio.emit('stream_event', {
                            'type': 'system.init',
                            'data': {
                                'session_id': event.get('session_id'),
                                'model': event.get('model'),
                                'tools': len(event.get('tools', []))
                            }
                        }, to=sid)

                    elif event_type == 'message_start':
                        await self.sio.emit('stream_event', {
                            'type': 'message.start',
                            'data': {
                                'message_id': event.get('message_id'),
                                'model': event.get('model')
                            }
                        }, to=sid)

                    elif event_type == 'content_delta':
                        # Text content streaming
                        await self.sio.emit('stream_event', {
                            'type': 'message.delta',
                            'data': {'content': event.get('content', '')}
                        }, to=sid)

                        if first_chunk:
                            logger.info(f"First chunk in {event['timestamp']:.2f}s")
                            first_chunk = False

                    elif event_type == 'tool_start':
                        current_tool_name = event.get('tool_name')
                        await self.sio.emit('stream_event', {
                            'type': 'tool.start',
                            'data': {
                                'tool_id': event.get('tool_id'),
                                'tool_name': current_tool_name
                            }
                        }, to=sid)
                        logger.info(f"Tool started: {current_tool_name}")

                    elif event_type == 'tool_input_delta':
                        # Show tool parameters being built
                        await self.sio.emit('stream_event', {
                            'type': 'tool.input_building',
                            'data': {
                                'tool_id': event.get('tool_id'),
                                'tool_name': event.get('tool_name'),
                                'partial_input': event.get('partial_input'),
                                'complete_input': event.get('complete_input')
                            }
                        }, to=sid)

                    elif event_type == 'tool_result':
                        # Tool execution result
                        await self.sio.emit('stream_event', {
                            'type': 'tool.result',
                            'data': {
                                'tool_id': event.get('tool_id'),
                                'content': event.get('content'),
                                'is_error': event.get('is_error', False)
                            }
                        }, to=sid)
                        logger.info(f"Tool result received for {current_tool_name}")

                    elif event_type == 'message_stop':
                        await self.sio.emit('stream_event', {
                            'type': 'message.stop',
                            'data': {}
                        }, to=sid)

                    elif event_type == 'complete':
                        # Send complete event
                        await self.sio.emit('stream_event', {
                            'type': 'session.complete',
                            'data': {
                                'total_time': event.get('total_time')
                            }
                        }, to=sid)
                        logger.info(f"Response completed in {event.get('total_time', 0):.2f}s")

                    elif event_type == 'error':
                        await self.sio.emit('stream_event', {
                            'type': 'error',
                            'data': {
                                'message': event.get('content', 'Unknown error')
                            }
                        }, to=sid)
                        logger.error(f"Error in stream: {event.get('content')}")

                # End streaming
                await self.sio.emit('stream_end', {}, to=sid)

            except Exception as e:
                # Only log actual errors, not normal completion
                if "normal completion" not in str(e).lower():
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
║     Claude Direct Interface - STREAM-JSON MODE         ║
╠════════════════════════════════════════════════════════╣
║                                                        ║
║  🌐 URL:  http://localhost:{self.port:<5}                        ║
║  ⚡ Mode: Stream-JSON with tool visibility            ║
║  🚀 First byte: <1 second (FIXED!)                   ║
║  🔧 Tools: Bash, Read, Edit, Write visible           ║
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