# Meal Planning Architecture

## Overview

ChefLink provides two complementary meal planning approaches, each serving different use cases and user needs.

## Services

### 1. MealPlanningService (`meal_planning_service.py`)

**Purpose**: Rule-based, deterministic meal planning with precise nutritional targeting.

**Key Features**:
- Calculates exact calorie and macro distributions
- Uses mathematical allocation for meal distribution (30% breakfast, 40% lunch, 30% dinner)
- Filters recipes based on strict nutritional criteria
- Predictable, consistent results
- Fast execution (no LLM calls)

**Use Cases**:
- Users with specific calorie/macro targets
- Meal prep with exact nutritional requirements
- Quick meal plan generation
- Batch meal planning for multiple days

**Example Flow**:
```python
# User wants 2000 calories with 150g protein
service = MealPlanningService(db, recipe_service)
plans = await service.create_intelligent_meal_plan(
    user_id=user.id,
    date=date.today(),
    preferences={"target_calories": 2000, "target_protein": 150}
)
```

### 2. MealPlanningAgent (`meal_planning_agent.py`)

**Purpose**: AI-powered, conversational meal planning with contextual understanding.

**Key Features**:
- Uses LLM (Claude/GPT) for intelligent reasoning
- Understands complex dietary preferences and restrictions
- Considers meal variety and flavor profiles
- Provides explanations and substitutions
- Adapts to conversational context
- Can handle vague requests ("something light for dinner")

**Use Cases**:
- Personalized meal recommendations
- Complex dietary requirements (multiple allergies, cultural preferences)
- Conversational meal planning
- Recipe discovery and exploration
- Meal plan adjustments based on feedback

**Example Flow**:
```python
# User asks: "I want Mediterranean meals this week, but I'm allergic to shellfish"
agent = MealPlanningAgent(llm_service)
response = await agent.process_request(
    user_request="Mediterranean meals, no shellfish",
    user_context=user_preferences,
    available_recipes=recipes
)
```

## When to Use Which Service

### Use MealPlanningService when:
- ✅ Exact nutritional targets are critical
- ✅ Speed is important (bulk operations)
- ✅ Predictable, consistent results needed
- ✅ Simple filtering criteria suffice
- ✅ No conversational context required

### Use MealPlanningAgent when:
- ✅ Natural language understanding needed
- ✅ Complex dietary preferences
- ✅ Conversational interaction
- ✅ Meal variety and creativity important
- ✅ Explanations and reasoning required
- ✅ Handling edge cases and special requests

## Integration in Handlers

The `FamilyHandlerV3` intelligently routes between these services:

1. **Direct Requests** → MealPlanningService
   - `/myplan` command
   - Specific calorie/macro requests
   - Quick meal generation

2. **Conversational Requests** → MealPlanningAgent
   - Natural language queries
   - Complex requirements
   - Interactive planning sessions

## Architecture Benefits

**Separation of Concerns**:
- Clear boundaries between AI and algorithmic approaches
- Easy to test and maintain separately
- Can be scaled independently

**Flexibility**:
- Users can choose their preferred interaction style
- Fallback from agent to service if LLM unavailable
- Mix approaches (agent for selection, service for allocation)

**Performance**:
- Service handles bulk operations efficiently
- Agent provides rich interactions when needed
- Optimal resource usage

## Future Enhancements

1. **Hybrid Approach**: Use agent for recipe selection, service for nutritional optimization
2. **Learning Loop**: Agent learns from service's successful plans
3. **Preference Migration**: Agent discoveries update service filters
4. **Parallel Processing**: Both generate plans, user chooses

## Code Organization

```
app/services/
├── meal_planning_service.py    # Algorithmic, rule-based planning
├── meal_planning_agent.py      # AI-powered, conversational planning
└── telegram/handlers/
    └── family_v3_refactored.py  # Routes to appropriate service
```

This dual-service architecture ensures ChefLink can handle both structured nutritional planning and flexible conversational meal recommendations effectively.