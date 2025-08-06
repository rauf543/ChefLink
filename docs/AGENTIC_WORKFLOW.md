# Agentic Workflow Implementation

## Overview

The agentic workflow implementation allows ChefLink's AI assistant to think iteratively through problems, using tools and reasoning across multiple steps before providing a final response to the user. This creates a more intelligent and thorough meal planning experience.

## Architecture

### Key Components

1. **Iterative Processing Loop**: The agent can think through up to 20 iterations
2. **Final Message Sentinel**: Uses `{{final_message: ...}}` to indicate completion
3. **Tool Execution**: Can use tools multiple times to refine results
4. **Cost & Safety Controls**: Limits on iterations, time, and spending
5. **Hidden Chain-of-Thought**: Users only see the final response

### Flow Diagram

```
User Message
    ↓
Initial Claude Call
    ↓
┌─→ Parse Response
│   ├─ Check for {{final_message: ...}}
│   │   └─ If found → Send to user → END
│   ├─ Check for tool calls
│   │   └─ If found → Execute tools
│   └─ Continue thinking
│       ↓
│   Check limits (time/cost/iterations)
│       ↓
│   Compress history if needed
│       ↓
└── Next Claude Call
```

## Configuration

### Feature Flags

Enable the agentic workflow using feature flags:

```bash
# Enable for specific users
python scripts/toggle_agentic_workflow.py --enable --users 123456 789012

# Enable with percentage rollout
python scripts/toggle_agentic_workflow.py --enable --percentage 25

# Disable
python scripts/toggle_agentic_workflow.py --disable
```

### Environment Variables

```bash
# In .env or docker-compose.yml
CHEFLINK_FEATURE_FLAGS='{"agentic_workflow": {"enabled": true, "rollout_percentage": 100}}'
```

### Configurable Parameters

In `FamilyHandlersV2Agentic`:
- `MAX_ITERATIONS = 20` - Maximum thinking iterations
- `MAX_TIME_SECONDS = 60` - Timeout for processing
- `MAX_TOKENS_PER_CALL = 8000` - Tokens per Claude call
- `COST_LIMIT = 0.50` - Maximum cost per conversation

## Usage Examples

### Simple Query
```
User: "Hello"
Agent: {{final_message: Hello! How can I help you with meal planning today?}}
Result: 1 iteration, immediate response
```

### Complex Query
```
User: "Plan healthy dinners for the week, but no fish on consecutive days"
Agent: Let me search for healthy dinner recipes...
       [Searches recipes]
       I found several options. Let me create a balanced plan...
       [Creates meal plan]
       I need to adjust to avoid consecutive fish days...
       [Updates plan]
       {{final_message: I've created a week of healthy dinners for you...}}
Result: 4 iterations, multiple tool uses
```

## Safety Features

1. **Tool Allowlist**: Only approved tools can be executed
2. **Cost Tracking**: Monitors API spending per conversation
3. **Timeout Protection**: Prevents infinite loops
4. **Token Management**: Compresses history to stay within limits
5. **Result Truncation**: Large tool results are summarized

## Monitoring & Debugging

### Tool Traces

Every conversation is traced with:
- Timestamp and duration of each iteration
- Tools executed with arguments
- Cost accumulation
- Error tracking

Access traces:
```python
trace_summary = handler.get_trace_summary(trace_id)
```

### Logs

Key log points:
- Feature flag decisions: `"Using agentic workflow for user {user_id}"`
- Cost limits: `"Cost limit reached: ${total_cost:.2f}"`
- Timeouts: `"Timeout after {iteration_count} iterations"`

## Testing

### Unit Tests
```bash
pytest tests/test_agentic_workflow.py
```

### Load Tests
```bash
python tests/load_test_scenarios.py
```

Expected metrics:
- Success rate: >95%
- Average response time: <5s for simple, <15s for complex
- Cost per query: <$0.10 average

## Rollout Plan

### Phase 1: Internal Testing (Day 1)
- Enable for development team
- Run load tests
- Monitor traces and costs

### Phase 2: Beta Users (Day 2-3)
- Enable for 10% of users
- Monitor error rates
- Collect feedback

### Phase 3: Full Rollout (Day 4+)
- Gradual increase to 100%
- A/B testing vs old workflow
- Performance optimization

## Troubleshooting

### Common Issues

1. **"Taking too long to think"**
   - Reduce MAX_ITERATIONS
   - Check for inefficient tool use patterns

2. **High costs**
   - Reduce MAX_TOKENS_PER_CALL
   - Implement more aggressive compression

3. **Not finding final message**
   - Check system prompt formatting
   - Verify regex pattern matching

### Debug Mode

Enable debug mode in feature flags:
```json
{
  "debug_mode": {
    "enabled": true,
    "log_traces": true,
    "log_costs": true
  }
}
```

## Performance Optimization

1. **Token Usage**
   - Start with 8k tokens, increase if needed
   - Compress old messages aggressively

2. **Tool Efficiency**
   - Cache frequent recipe searches
   - Batch similar operations

3. **Response Time**
   - Show progress indicators
   - Stream partial results if possible

## Future Enhancements

1. **Parallel Tool Execution**: Run independent tools concurrently
2. **Streaming Responses**: Send partial final messages as generated
3. **Learning from Traces**: Use successful patterns to improve prompts
4. **Dynamic Limits**: Adjust limits based on query complexity