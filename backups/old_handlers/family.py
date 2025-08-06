import json
import logging
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from telegram import Update
from telegram.ext import ContextTypes

from app.core.schemas.recipe import RecipeSearch
from app.database.base import AsyncSessionLocal
from app.database.models import MealPlan, MealPlanStatus, MealType, Recipe, User
from app.services.llm.factory import get_llm_service
from app.services.recipe_service import RecipeService
from app.services.telegram.utils import format_meal_plan_summary, get_user_by_telegram_id

logger = logging.getLogger(__name__)


class FamilyHandlers:
    """Handlers for family member users."""
    
    def __init__(self):
        self.llm_service = get_llm_service()
        
    async def start_meal_planning(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Start the meal planning process."""
        user_id = str(update.effective_user.id)
        
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_id(db, user_id)
            
            if not user or user.role.value != 'family_member':
                await update.message.reply_text(
                    "This command is only available for family members."
                )
                return
                
            await update.message.reply_text(
                "Let's plan your meals! 🍽️\n\n"
                "I'll ask you a few questions to understand your preferences.\n\n"
                "How many days would you like to plan for? (e.g., '7 days', 'next week')"
            )
            
            # Store conversation state
            context.user_data['meal_planning_active'] = True
            context.user_data['user_id'] = str(user.id)
            
    async def show_meal_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show the user's current meal plan."""
        user_id = str(update.effective_user.id)
        
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_id(db, user_id)
            
            if not user:
                await update.message.reply_text(
                    "Please register first using /start command."
                )
                return
                
            # Get meal plans for next 7 days
            today = date.today()
            end_date = today + timedelta(days=7)
            
            result = await db.execute(
                select(MealPlan)
                .where(MealPlan.user_id == user.id)
                .where(MealPlan.date >= today)
                .where(MealPlan.date < end_date)
                .order_by(MealPlan.date, MealPlan.meal_type)
                .options(
                    selectinload(MealPlan.recipe)
                )
            )
            
            meal_plans = result.scalars().all()
            
            if not meal_plans:
                await update.message.reply_text(
                    "You don't have any meal plans scheduled.\n"
                    "Use /plan to start planning your meals!"
                )
                return
                
            summary = format_meal_plan_summary(meal_plans)
            await update.message.reply_text(
                f"📋 *Your Meal Plan*\n\n{summary}",
                parse_mode='Markdown'
            )
            
    async def search_recipes(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Search for recipes."""
        # Extract search query from command
        text = update.message.text.split(' ', 1)
        if len(text) < 2:
            await update.message.reply_text(
                "Please provide a search term.\n"
                "Example: /search chicken"
            )
            return
            
        search_term = text[1]
        
        async with AsyncSessionLocal() as db:
            recipe_service = RecipeService(db)
            
            search_params = RecipeSearch(
                name=search_term,
                limit=5
            )
            
            recipes = await recipe_service.search_recipes(search_params)
            
            if not recipes:
                await update.message.reply_text(
                    f"No recipes found for '{search_term}'."
                )
                return
                
            message = f"🔍 *Search results for '{search_term}':*\n\n"
            
            for recipe in recipes:
                message += (
                    f"• *{recipe.recipe_name}*\n"
                    f"  📊 {recipe.calories_per_serving} cal | "
                    f"🥩 {recipe.macro_nutrients['protein_g']}g protein\n"
                )
                if recipe.main_protein:
                    message += f"  🍖 Main: {', '.join(recipe.main_protein)}\n"
                message += "\n"
                
            await update.message.reply_text(message, parse_mode='Markdown')
            
    async def handle_conversation(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        user: User,
        db: AsyncSession
    ) -> None:
        """Handle conversational interface for family members."""
        if not context.user_data.get('meal_planning_active'):
            # Use LLM to understand user intent
            await self._handle_general_conversation(update, context, user, db)
        else:
            # Continue meal planning conversation
            await self._handle_meal_planning_conversation(update, context, user, db)
            
    async def _handle_general_conversation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: User,
        db: AsyncSession
    ) -> None:
        """Handle general conversation with AI agent."""
        user_message = update.message.text
        
        # Create a prompt for the LLM to act as a meal planning assistant
        system_prompt = """You are ChefLink, a friendly meal planning assistant. You help family members:
1. Plan their meals
2. Modify existing meal plans
3. Find recipes based on preferences
4. Track nutritional goals

You have access to these capabilities:
- Search recipes by name, calories, protein content
- Create and modify meal plans
- Calculate nutritional information

Respond conversationally and helpfully. If the user wants to start meal planning, tell them to use /plan.
If they want to search for specific recipes, tell them to use /search <recipe name>.
"""

        try:
            response = await self.llm_service.client.messages.create(
                model=self.llm_service.model,
                max_tokens=1000,
                temperature=0.7,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_message
                    }
                ],
                thinking={
                    "type": "enabled",
                    "budget_tokens": 4000
                }
            )
            
            await update.message.reply_text(response.content[0].text)
            
        except Exception as e:
            logger.error(f"Error in conversation: {str(e)}")
            await update.message.reply_text(
                "I'm having trouble understanding. Could you please rephrase?"
            )
            
    async def _handle_meal_planning_conversation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: User,
        db: AsyncSession
    ) -> None:
        """Handle meal planning conversation flow."""
        user_message = update.message.text
        
        # This is a simplified version - in production, you'd have a more sophisticated
        # conversation flow with Claude managing the state
        
        if 'duration' not in context.user_data:
            context.user_data['duration'] = user_message
            await update.message.reply_text(
                "Great! Now, what are your dietary goals?\n"
                "For example: '2200 calories, high protein' or 'vegetarian, 1800 calories'"
            )
            
        elif 'goals' not in context.user_data:
            context.user_data['goals'] = user_message
            await update.message.reply_text(
                "Perfect! How many meals do you eat per day and do you have any preferences?\n"
                "For example: '3 meals, light breakfast' or '2 meals and 2 snacks'"
            )
            
        elif 'habits' not in context.user_data:
            context.user_data['habits'] = user_message
            
            # Now use Claude to generate the meal plan
            await update.message.reply_text(
                "Excellent! Let me create a personalized meal plan for you... 🤔"
            )
            
            # Generate meal plan using Claude
            await self._generate_meal_plan(update, context, user, db)
            
            # Clear planning state
            context.user_data.clear()
            
    async def _generate_meal_plan(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: User,
        db: AsyncSession
    ) -> None:
        """Generate meal plan using Claude and available recipes."""
        duration = context.user_data.get('duration', '7 days')
        goals = context.user_data.get('goals', '2000 calories')
        habits = context.user_data.get('habits', '3 meals per day')
        
        try:
            # Parse duration to get number of days
            days = 7  # default
            if 'day' in duration.lower():
                import re
                match = re.search(r'(\d+)', duration)
                if match:
                    days = int(match.group(1))
            
            # Get all available recipes
            from sqlalchemy import select
            result = await db.execute(select(Recipe))
            recipes = result.scalars().all()
            
            if not recipes:
                await update.message.reply_text(
                    "❌ No recipes available in the database. Please ask an admin to add some recipes first."
                )
                return
            
            # Create meal plans for the specified duration
            from datetime import date, timedelta
            import random
            
            start_date = date.today()
            meal_types = [MealType.BREAKFAST, MealType.LUNCH, MealType.DINNER]
            
            created_count = 0
            for day_offset in range(days):
                plan_date = start_date + timedelta(days=day_offset)
                
                for meal_type in meal_types:
                    # Simple random selection - in production, use Claude for smart selection
                    recipe = random.choice(recipes)
                    
                    meal_plan = MealPlan(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        date=plan_date,
                        recipe_id=recipe.id,
                        meal_type=meal_type,
                        servings=1,
                        status=MealPlanStatus.UNLOCKED,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(meal_plan)
                    created_count += 1
            
            await db.commit()
            
            await update.message.reply_text(
                f"✅ Meal plan created!\n\n"
                f"📅 Duration: {days} days\n"
                f"🎯 Goals: {goals}\n"
                f"🍽️ Habits: {habits}\n"
                f"📊 Total meals planned: {created_count}\n\n"
                f"Use /myplan to view your meal plan.\n"
                f"You can ask me to modify specific meals anytime!"
            )
            
        except Exception as e:
            logger.error(f"Error generating meal plan: {str(e)}")
            await update.message.reply_text(
                "❌ Sorry, I encountered an error while creating your meal plan. Please try again."
            )