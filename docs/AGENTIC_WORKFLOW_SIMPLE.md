# ChefLink Agentic Workflow

## How It Works

The ChefLink bot uses an iterative thinking process to provide better meal planning assistance:

1. **The bot thinks step-by-step** - It can search recipes, analyze options, and refine its approach
2. **Multiple iterations allowed** - Up to 20 thinking steps before responding
3. **Users only see the final answer** - All the thinking happens behind the scenes
4. **Tools can be used multiple times** - Search different recipes, compare options, etc.

## The Magic Marker

The bot knows it's ready to respond when it writes:
```
{{final_message: Your response here}}
```

Everything before this marker is hidden thinking. Only the final message is sent to users.

## Example Flow

```
User: "Find me healthy breakfast recipes"

Bot (thinking, hidden):
- Let me search for breakfast recipes under 300 calories
- [Searches recipes]
- Found 5 options, let me filter for high protein
- [Searches again with protein filter]
- Good options found, let me summarize

Bot (to user):
"I found 3 great healthy breakfast options for you:
1. Greek Yogurt Parfait (220 cal, 18g protein)
2. Veggie Egg Cups (180 cal, 15g protein)  
3. Overnight Oats (250 cal, 10g protein)"
```

## Configuration

The only setting is `MAX_ITERATIONS = 20` in `family_v2_agentic.py`

That's it! No feature flags, no complex configuration. The bot just works smarter.

## To Deploy

```bash
# Just restart the bot
docker-compose restart bot
```

The agentic workflow is now the default and only workflow.