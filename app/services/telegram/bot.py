import logging
from datetime import datetime, time, timedelta
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.core.config import settings
from app.database.base import AsyncSessionLocal
from app.database.models import MealPlanStatus, UserRole
from app.services.telegram.handlers.chef import ChefHandlers
from app.services.telegram.handlers.family_v3_refactored import FamilyHandlerV3
from app.services.telegram.handlers.shared import SharedHandlers
from app.services.telegram.utils import States, get_user_by_telegram_id

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class ChefLinkBot:
    def __init__(self):
        self.application = (
            Application.builder()
            .token(settings.TELEGRAM_BOT_TOKEN)
            .build()
        )
        self.shared_handlers = SharedHandlers()
        # Unified family handler replaces v1, v2, and v2_agentic
        self.family_handler = FamilyHandlerV3  # Class, not instance - will be instantiated per request
        self.chef_handlers = ChefHandlers()
        
    def setup_handlers(self):
        """Set up all bot handlers."""
        # Registration conversation
        registration_conv = ConversationHandler(
            entry_points=[
                CommandHandler("start", self.shared_handlers.start),
                CommandHandler("register", self.shared_handlers.start),
            ],
            states={
                States.INVITATION_CODE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.shared_handlers.verify_invitation)
                ],
                States.NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.shared_handlers.get_name)
                ],
                States.ROLE: [
                    CallbackQueryHandler(self.shared_handlers.select_role)
                ],
            },
            fallbacks=[CommandHandler("cancel", self.shared_handlers.cancel)],
        )
        
        self.application.add_handler(registration_conv)
        
        # Family member handlers
        self.application.add_handler(
            CommandHandler("myplan", self.handle_myplan_command)
        )
        self.application.add_handler(
            CommandHandler("search", self.handle_search_command)
        )
        # Clear command not needed for agentic workflow since history is managed differently
        
        # Chef handlers
        self.application.add_handler(
            CommandHandler("mealplan", self.chef_handlers.get_daily_meal_plan)
        )
        self.application.add_handler(
            CommandHandler("shoppinglist", self.chef_handlers.generate_shopping_list)
        )
        
        # General handlers
        self.application.add_handler(
            CommandHandler("help", self.shared_handlers.help_command)
        )
        
        # Message handler for conversational interface
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
        
        # Schedule daily meal plan locking
        self.schedule_daily_tasks()
        
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle general messages based on user role."""
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_id(db, str(update.effective_user.id))
            
            if not user:
                await update.message.reply_text(
                    "Please register first using /start command."
                )
                return
                
            if user.role == UserRole.FAMILY_MEMBER:
                # Use the unified handler for all family members
                handler = self.family_handler(db)
                await handler.handle_message(update, context, user)
            else:
                await update.message.reply_text(
                    "As a chef, please use specific commands:\n"
                    "/mealplan - Get today's meal plan\n"
                    "/shoppinglist - Generate shopping list"
                )
                
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log errors caused by updates."""
        logger.error(msg="Exception while handling an update:", exc_info=context.error)
        
        # Log the full error details
        import traceback
        logger.error(f"Full error traceback:\n{traceback.format_exc()}")
        
        if isinstance(update, Update) and update.effective_message:
            error_message = "Sorry, an error occurred while processing your request.\n\n"
            if context.error:
                error_message += f"Error: {str(context.error)[:200]}"
            await update.effective_message.reply_text(error_message)
            
    def schedule_daily_tasks(self):
        """Schedule daily tasks like meal plan locking."""
        try:
            job_queue = self.application.job_queue
            
            if job_queue is None:
                logger.warning("JobQueue not available. Daily tasks will not be scheduled.")
                return
                
            # Schedule meal plan locking at 8 PM daily
            lock_time = time(hour=settings.MEAL_PLAN_LOCK_HOUR, minute=0, second=0)
            job_queue.run_daily(self.lock_meal_plans, lock_time)
            logger.info(f"Scheduled daily meal plan locking at {lock_time}")
        except Exception as e:
            logger.error(f"Failed to schedule daily tasks: {e}")
        
    async def lock_meal_plans(self, context: ContextTypes.DEFAULT_TYPE):
        """Lock meal plans for the next day."""
        tomorrow = datetime.now().date() + timedelta(days=1)
        
        async with AsyncSessionLocal() as db:
            from sqlalchemy import update
            from app.database.models import MealPlan
            
            stmt = (
                update(MealPlan)
                .where(MealPlan.date == tomorrow)
                .where(MealPlan.status == MealPlanStatus.UNLOCKED)
                .values(status=MealPlanStatus.LOCKED)
            )
            
            await db.execute(stmt)
            await db.commit()
            
            logger.info(f"Locked meal plans for {tomorrow}")
            
    async def handle_myplan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /myplan command using unified handler."""
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_id(db, str(update.effective_user.id))
            if user and user.role == UserRole.FAMILY_MEMBER:
                # For now, forward to message handler with appropriate text
                update.message.text = "Show me my meal plan for today"
                handler = self.family_handler(db)
                await handler.handle_message(update, context, user)
            else:
                await update.message.reply_text("This command is only for family members.")
    
    async def handle_search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /search command using unified handler."""
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_id(db, str(update.effective_user.id))
            if user and user.role == UserRole.FAMILY_MEMBER:
                query = ' '.join(context.args) if context.args else ""
                if not query:
                    await update.message.reply_text("Please provide a search query. Example: /search chicken salad")
                    return
                handler = self.family_handler(db)
                await handler.handle_recipe_search(update, context, user, query)
            else:
                await update.message.reply_text("This command is only for family members.")
    
    def run(self):
        """Run the bot."""
        self.setup_handlers()
        logger.info("Bot is starting...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)