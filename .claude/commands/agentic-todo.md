# Agentic Claude Interface - Enhancement Roadmap

## Vision
Transform the Open Chat Interface into a fully agentic web-based version of OpenCode, providing complete transparency and control over Claude's actions while maintaining the simplicity of a browser interface.

## Core Requirements

### 1. Full Streaming with Tool Visibility
**Goal**: See everything Claude is doing in real-time

**Implementation**:
- Switch from `--print` mode to `--output-format stream-json`
- Parse streaming JSON events to capture:
  - Tool calls (Bash, Edit, Read, Write, etc.)
  - File access patterns
  - Partial message chunks
  - Error events

**Backend Changes**:
```python
# New streaming command
cmd = [
    'claude',
    '--output-format', 'stream-json',
    '--include-partial-messages',
    '--input-format', 'stream-json',
    '--replay-user-messages'
]

# Parse streaming events
async def parse_stream_event(line):
    event = json.loads(line)
    if event['type'] == 'tool_use':
        await emit_tool_event(event)
    elif event['type'] == 'content_block_delta':
        await emit_content_delta(event)
```

**Frontend Display**:
- Split view: Chat on left, Tool Activity on right
- Real-time tool execution timeline
- Syntax-highlighted command display

### 2. Interactive Feedback System
**Goal**: Allow user to approve/deny actions and provide feedback

**Features**:
- Approval dialogs for dangerous operations (file edits, deletions)
- Option selection when Claude asks for choices
- Ability to stop execution mid-stream

**Implementation**:
```javascript
// Frontend feedback handler
socket.on('feedback_request', async (data) => {
    const response = await showFeedbackDialog({
        title: data.title,
        options: data.options,
        default: data.default
    });
    socket.emit('feedback_response', {
        request_id: data.id,
        response: response
    });
});
```

**Backend Queue System**:
```python
class FeedbackManager:
    def __init__(self):
        self.pending_requests = {}

    async def request_feedback(self, sid, request_type, options):
        request_id = str(uuid.uuid4())
        self.pending_requests[request_id] = asyncio.Future()

        await sio.emit('feedback_request', {
            'id': request_id,
            'type': request_type,
            'options': options
        }, to=sid)

        return await self.pending_requests[request_id]
```

### 3. File System Integration
**Goal**: Track and display all file operations

**Features**:
- Live file tree of accessed files
- Before/after diffs for edits
- File preview sidebar
- Directory browsing

**Implementation**:
```python
class FileTracker:
    def __init__(self):
        self.accessed_files = set()
        self.file_history = []

    def track_access(self, file_path, operation):
        self.accessed_files.add(file_path)
        self.file_history.append({
            'path': file_path,
            'operation': operation,
            'timestamp': datetime.now()
        })
```

**UI Components**:
- File Explorer (VSCode-like tree view)
- Diff Viewer (Monaco Editor integration)
- File History Timeline

### 4. Tool Control & Permissions
**Goal**: Fine-grained control over what Claude can do

**Features**:
- Tool allowlist/denylist configuration
- Permission profiles (read-only, safe-edit, full-access)
- Per-session permission overrides

**Implementation**:
```python
# Permission profiles
PERMISSION_PROFILES = {
    'read_only': {
        'allowed_tools': ['Read', 'Glob', 'Grep'],
        'disallowed_tools': ['*']
    },
    'safe_edit': {
        'allowed_tools': ['Read', 'Edit', 'Glob', 'Grep'],
        'disallowed_tools': ['Bash', 'Write']
    },
    'full_access': {
        'allowed_tools': ['*'],
        'disallowed_tools': []
    }
}

# Apply permissions to Claude command
def build_claude_command(profile='safe_edit'):
    cmd = ['claude', '--output-format', 'stream-json']

    if profile in PERMISSION_PROFILES:
        allowed = PERMISSION_PROFILES[profile]['allowed_tools']
        if allowed:
            cmd.extend(['--allowed-tools', ' '.join(allowed)])

    return cmd
```

**UI Controls**:
- Permission selector dropdown
- Tool toggle switches
- Resource limit settings

### 5. Enhanced Streaming Protocol
**Goal**: Bidirectional streaming for real-time interaction

**Features**:
- Send messages while Claude is responding
- Interrupt/redirect Claude mid-execution
- Context injection during conversation

**Implementation**:
```python
class StreamingSession:
    def __init__(self):
        self.process = None
        self.input_queue = asyncio.Queue()
        self.output_queue = asyncio.Queue()

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(
            'claude',
            '--input-format', 'stream-json',
            '--output-format', 'stream-json',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE
        )

        # Start input/output handlers
        asyncio.create_task(self.handle_input())
        asyncio.create_task(self.handle_output())

    async def send_message(self, content):
        await self.input_queue.put({
            'type': 'message',
            'content': content
        })
```

### 6. MCP Server Integration
**Goal**: Extend Claude's capabilities with MCP servers

**Features**:
- Browser automation (Playwright MCP)
- Database access
- Custom tool servers
- API integrations

**Configuration**:
```json
{
  "mcp_servers": [
    {
      "name": "browser",
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    },
    {
      "name": "database",
      "command": "python",
      "args": ["mcp_sqlite_server.py"]
    }
  ]
}
```

**Launch Command**:
```python
cmd = [
    'claude',
    '--mcp-config', json.dumps(mcp_config),
    '--strict-mcp-config'
]
```

## Implementation Phases

### Phase 1: Core Streaming (Week 1)
- [ ] Implement stream-json parsing
- [ ] Create event dispatcher
- [ ] Update frontend for streaming events
- [ ] Add basic tool visibility

### Phase 2: Interactive Feedback (Week 2)
- [ ] Build feedback request/response system
- [ ] Create approval dialogs
- [ ] Implement execution interruption
- [ ] Add option selection UI

### Phase 3: File System (Week 3)
- [ ] Create file tracker
- [ ] Build file explorer UI
- [ ] Implement diff viewer
- [ ] Add file preview

### Phase 4: Permissions (Week 4)
- [ ] Define permission profiles
- [ ] Build permission UI
- [ ] Implement tool filtering
- [ ] Add resource limits

### Phase 5: Advanced Features (Week 5-6)
- [ ] MCP server configuration
- [ ] Session management improvements
- [ ] Export/import conversations
- [ ] Collaborative features

## Technical Architecture

### Backend Components
```
backend/
├── server.py           # Main server
├── streaming.py        # Stream JSON handler
├── feedback.py         # Feedback manager
├── permissions.py      # Permission system
├── file_tracker.py     # File operation tracking
├── mcp_config.py       # MCP server management
└── session_manager.py  # Enhanced sessions
```

### Frontend Components
```
frontend/
├── index.html          # Main UI
├── js/
│   ├── chat.js        # Chat interface
│   ├── tools.js       # Tool visibility
│   ├── feedback.js    # Feedback dialogs
│   ├── files.js       # File explorer
│   └── permissions.js # Permission controls
└── css/
    ├── main.css       # Main styles
    └── components.css # Component styles
```

### WebSocket Events

**Client → Server**:
- `send_message`: Send user message
- `feedback_response`: Respond to feedback request
- `update_permissions`: Change permission settings
- `interrupt_execution`: Stop current execution
- `request_file_preview`: Get file contents

**Server → Client**:
- `stream_event`: All streaming events
- `feedback_request`: Request user feedback
- `tool_event`: Tool execution updates
- `file_event`: File operation notifications
- `permission_event`: Permission changes

## UI Mockup

```
┌─────────────────────────────────────────────────────────────┐
│ Claude Interface  [Settings] [Permissions: Safe Edit ▼]     │
├─────────────────────────────┬───────────────────────────────┤
│                             │ Tool Activity                  │
│ Chat                        ├───────────────────────────────┤
│                             │ ▶ Bash: ls -la               │
│ You: Help me fix bug.py     │   Output: file1.py, file2.py │
│                             │                               │
│ Claude: I'll help you fix   │ ▶ Read: bug.py               │
│ the bug. Let me first look  │   Reading 150 lines...       │
│ at the file...              │                               │
│                             │ ⚠ Edit: bug.py               │
│ [Currently reading bug.py]  │   [Approve] [Deny] [View]    │
│                             │                               │
├─────────────────────────────┼───────────────────────────────┤
│ [Type message...]    [Send] │ Files Accessed: 3            │
└─────────────────────────────┴───────────────────────────────┘
```

## Success Metrics

1. **Transparency**: User can see every action Claude takes
2. **Control**: User can approve/deny dangerous operations
3. **Performance**: <100ms latency for streaming events
4. **Reliability**: Graceful handling of errors and disconnections
5. **Usability**: Intuitive UI that doesn't overwhelm users

## Security Considerations

1. **Input Sanitization**: Validate all user inputs
2. **Path Traversal**: Prevent access outside allowed directories
3. **Command Injection**: Sanitize tool arguments
4. **Rate Limiting**: Prevent abuse of resources
5. **Session Isolation**: Ensure sessions don't interfere

## Future Vision

### V2.0 - Collaboration
- Multi-user sessions
- Shared workspaces
- Real-time collaboration
- Comment threads on code

### V3.0 - Intelligence
- Auto-permission suggestions
- Risk assessment for operations
- Smart file change batching
- Predictive feedback requests

### V4.0 - Platform
- Plugin system for custom tools
- Marketplace for MCP servers
- Custom UI themes
- API for third-party integrations

## Development Guidelines

1. **Progressive Enhancement**: Start simple, add features incrementally
2. **User-Centric Design**: Every feature should solve a real user problem
3. **Performance First**: Optimize for responsiveness and low latency
4. **Fail Gracefully**: Handle errors without breaking the experience
5. **Document Everything**: Clear documentation for users and developers

---

This roadmap transforms the basic chat interface into a powerful agentic system that gives users full visibility and control over Claude's actions, making it a true web-based alternative to OpenCode.