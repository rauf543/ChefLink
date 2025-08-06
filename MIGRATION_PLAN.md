# Migration Plan: Removing Redundant Handler Files

## Files to Remove (Redundant)

These files are now completely replaced by `family_v3_refactored.py`:

1. **`app/services/telegram/handlers/family.py`** (12KB)
   - Old handler with basic functionality
   - Completely superseded by v3

2. **`app/services/telegram/handlers/family_v2.py`** (44KB) 
   - Non-agentic v2 handler
   - All functionality moved to v3

3. **`app/services/telegram/handlers/family_v2_agentic.py`** (45KB)
   - Agentic v2 handler
   - All functionality moved to v3

**Total redundant code to remove: ~101KB**

## Migration Steps

### Step 1: Update Bot Initialization

Update `app/services/telegram/bot.py`:

```python
# OLD IMPORTS (REMOVE):
from app.services.telegram.handlers.family import FamilyHandlers
from app.services.telegram.handlers.family_v2_agentic import FamilyHandlersV2Agentic

# NEW IMPORT (ADD):
from app.services.telegram.handlers.family_v3_refactored import FamilyHandlerV3

# UPDATE __init__ method:
class ChefLinkBot:
    def __init__(self):
        self.application = (
            Application.builder()
            .token(settings.TELEGRAM_BOT_TOKEN)
            .build()
        )
        self.shared_handlers = SharedHandlers()
        self.family_handler = FamilyHandlerV3  # Single unified handler
        self.chef_handlers = ChefHandlers()
```

### Step 2: Update Handler Registration

Update handler setup in `bot.py` to use the new unified handler:

```python
async def handle_family_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route family messages to the unified handler."""
    async with AsyncSessionLocal() as db:
        user = await get_user_by_telegram_id(db, str(update.effective_user.id))
        if user and user.role == UserRole.FAMILY_MEMBER:
            handler = FamilyHandlerV3(db)
            await handler.handle_message(update, context, user)
```

### Step 3: Update Test Files

Update test imports in:
- `tests/test_agentic_workflow.py`
- `tests/load_test_scenarios.py`
- `test_family_v2_fixes.py`

### Step 4: Remove Redundant Files

```bash
# After confirming everything works
rm app/services/telegram/handlers/family.py
rm app/services/telegram/handlers/family_v2.py
rm app/services/telegram/handlers/family_v2_agentic.py
```

## Benefits of Migration

1. **Code Reduction**: Remove ~101KB of duplicate code
2. **Maintenance**: Single file to maintain instead of three
3. **Consistency**: One implementation ensures consistent behavior
4. **Performance**: Shared tool registry and executor reduce overhead
5. **Testing**: Single implementation to test

## Rollback Plan

If issues arise:
1. Git revert the changes
2. Re-import old handlers
3. Debug specific issues
4. Migrate gradually by running both in parallel

## Verification Checklist

- [ ] All tests pass with new handler
- [ ] Both response modes work (direct and agentic)
- [ ] Tool execution functions correctly
- [ ] Conversation context management works
- [ ] No regression in functionality
- [ ] Performance metrics maintained or improved