# Agent Design Mode Guide

## What is Design Mode?

Design Mode allows you to test and develop agents without making actual LLM API calls. When enabled, agents return mock responses, saving API costs and allowing faster iteration during development.

## How to Enable Design Mode

### Option 1: Environment Variable (Recommended)

Add to your `.env` file in `massive-trader/backend/`:

```bash
AGENT_DESIGN_MODE=true
```

### Option 2: Default Configuration

The default is `false` (normal mode). Set `AGENT_DESIGN_MODE=true` to enable.

## What Happens in Design Mode?

1. **No LLM Calls**: Agents skip actual API calls to Claude/Anthropic
2. **Mock Responses**: Agents return predefined test responses
3. **Faster Testing**: No API rate limits or costs
4. **Logging**: Special `🔧 [DESIGN MODE]` logs indicate mock responses

## Example Mock Response

When in design mode, agents return:
```python
AgentScore(
    score=65.0,
    sentiment=0.3,
    confidence=0.7,
    urgency=0.5,
    notes="[DESIGN MODE] Mock response from NewsAgent. Data keys: ['news_items']"
)
```

## Customizing Mock Responses

You can override `_get_design_mode_response()` in any agent subclass to return custom mock data:

```python
class MyCustomAgent(BaseAgent):
    def _get_design_mode_response(self, data: Dict[str, Any]) -> AgentScore:
        # Custom mock logic based on data
        if "urgent" in str(data):
            return AgentScore(score=85.0, sentiment=0.8, ...)
        return AgentScore(score=50.0, sentiment=0.0, ...)
```

## Usage Examples

### Testing Agent Logic
```bash
# Enable design mode
export AGENT_DESIGN_MODE=true

# Run your trading system
python -m app.main

# Agents will use mock responses
```

### Development Workflow
1. Enable design mode during development
2. Test agent logic and data processing
3. Disable design mode for final testing with real LLM calls

## Disabling Design Mode

Set in `.env`:
```bash
AGENT_DESIGN_MODE=false
```

Or remove the variable (defaults to `false`).

## Notes

- Design mode affects **all agents** (NewsAgent, EarningsAgent, etc.)
- Mock responses are consistent but not realistic
- Use design mode for development, disable for production
- Real trading decisions should always use real LLM responses

