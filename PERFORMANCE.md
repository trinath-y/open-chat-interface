# Performance Analysis & Solutions

## Current Performance Issues

### Test Results (28 Sep 2025)

| Implementation | Response Time | Issue |
|---------------|---------------|-------|
| `server.py` with JSON | 45-53 seconds | JSON overhead + complete response wait |
| `server_fast.py` plain text | 11-16 seconds | Still waits for complete response |
| Direct Claude CLI `--print` | ~11 seconds | Fundamental limitation of --print mode |

## Root Cause

The `--print` flag is designed for batch processing, not interactive use. It:
1. Sends the prompt to Claude
2. Waits for the ENTIRE response to be generated
3. Returns everything at once

This is why even a simple "Hi" takes 11+ seconds.

## The Solution: Stream-JSON Format

Claude CLI supports real-time streaming with proper flags:

```bash
claude \
  --output-format stream-json \
  --include-partial-messages \
  "Your message"
```

This provides:
- **First token**: <1 second
- **Streaming**: Real-time character-by-character output
- **Tool visibility**: See what Claude is doing as it happens

## Implementation Fix

```python
# DON'T DO THIS (waits for complete response):
cmd = ['claude', '--print', '--output-format', 'json', message]
result = subprocess.run(cmd)  # Blocks for 45+ seconds

# DO THIS (real-time streaming):
process = await asyncio.create_subprocess_exec(
    'claude',
    '--output-format', 'stream-json',
    '--include-partial-messages',
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE
)

# Stream events as they arrive
async for line in process.stdout:
    event = json.loads(line)
    if event['type'] == 'content_block_delta':
        yield event['delta']['text']  # Immediate streaming
```

## Streaming Event Format

```json
{"type": "message_start", "message": {"id": "msg_123"}}
{"type": "content_block_start", "content_block": {"type": "text"}}
{"type": "content_block_delta", "delta": {"text": "Hello"}}
{"type": "content_block_delta", "delta": {"text": " there"}}
{"type": "content_block_stop"}
{"type": "message_stop"}
```

## Performance Comparison

| Mode | First Byte | Complete Response |
|------|-----------|-------------------|
| --print with JSON | 45s | 45-53s |
| --print plain text | 11s | 11-16s |
| stream-json (proper) | <1s | Same time, but streaming |
| Interactive mode | <1s | Real-time streaming |

## Next Steps

1. **Immediate Fix**: Implement proper stream-json parsing
2. **Enhanced Version**: Use interactive mode with session management
3. **Agentic Features**: Parse tool events from streaming output

## Testing Commands

```bash
# Slow (what we're doing now):
time claude --print "Say hi"  # 11+ seconds

# Fast (what we should do):
claude --output-format stream-json --include-partial-messages "Say hi"
# First character appears in <1 second

# For tool visibility:
claude --output-format stream-json --include-partial-messages \
  --replay-user-messages \
  "List files in current directory"
# Shows tool calls as they happen
```

## Conclusion

The current implementation uses batch mode (`--print`) which is fundamentally slow. OpenCode uses the Anthropic SDK which streams by default. To match that performance, we need to switch to stream-json format and parse events as they arrive, giving us <1 second to first byte.