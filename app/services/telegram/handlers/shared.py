import logging
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from app.database.base import AsyncSessionLocal
from app.database.models import User, UserRole
from app.services.invitation_service import InvitationService
from app.services.telegram.utils import States, generate_invitation_code

logger = logging.getLogger(__name__)


class SharedHandlers:
    """Handlers shared between all users."""
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the registration process."""
        user_id = str(update.effective_user.id)
        
        # Check if user already exists
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                await update.message.reply_text(
                    f"Welcome back, {existing_user.name}! "
                    f"You're registered as a {existing_user.role.value.replace('_', ' ').title()}.\n\n"
                    f"Use /help to see available commands."
                )
                return ConversationHandler.END
                
        await update.message.reply_text(
            "Welcome to ChefLink! 🍳\n\n"
            "I'm your personal meal planning assistant. "
            "To get started, please enter your invitation code:"
        )
        
        return States.INVITATION_CODE
        
    async def verify_invitation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Verify the invitation code."""
        code = update.message.text.strip().upper()
        
        async with AsyncSessionLocal() as db:
            is_valid, role, error_message = await InvitationService.validate_invitation_code(code, db)
            
            if is_valid:
                context.user_data['invitation_code'] = code
                context.user_data['suggested_role'] = role
                await update.message.reply_text(
                    "Great! Your invitation code is valid. ✅\n\n"
                    "Now, please tell me your name:"
                )
                return States.NAME
            else:
                await update.message.reply_text(
                    f"❌ {error_message}\n\n"
                    "Please check your invitation code and try again.\n"
                    "Valid demo codes: CHEF2024, FAMILY24, DEMO1234"
                )
                return States.INVITATION_CODE
            
    async def get_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get the user's name."""
        name = update.message.text.strip()
        
        if len(name) < 2:
            await update.message.reply_text(
                "Please enter a valid name (at least 2 characters):"
            )
            return States.NAME
            
        context.user_data['name'] = name
        
        # Check if role is predetermined by invitation code
        suggested_role = context.user_data.get('suggested_role')
        
        if suggested_role:
            # Auto-assign role based on invitation code
            role_map = {
                "family_member": UserRole.FAMILY_MEMBER,
                "chef": UserRole.CHEF
            }
            selected_role = role_map.get(suggested_role, UserRole.FAMILY_MEMBER)
            
            # Create user directly
            async with AsyncSessionLocal() as db:
                user = User(
                    id=uuid.uuid4(),
                    telegram_id=str(update.effective_user.id),
                    name=name,
                    role=selected_role,
                    invitation_code=context.user_data['invitation_code']
                )
                
                db.add(user)
                await db.commit()
            
            role_name = selected_role.value.replace('_', ' ').title()
            welcome_message = f"Welcome to ChefLink, {name}! 🎉\n\n"
            
            if selected_role == UserRole.FAMILY_MEMBER:
                welcome_message += (
                    "As a Family Member, I'll help you:\n"
                    "• Plan your meals for the week\n"
                    "• Track your nutritional goals\n"
                    "• Discover new recipes\n\n"
                    "Just chat with me naturally about what you'd like to eat!"
                )
            else:
                welcome_message += (
                    "As a Chef, you can:\n"
                    "• View daily meal plans with /mealplan\n"
                    "• Generate shopping lists with /shoppinglist\n\n"
                    "Type /help for more information."
                )
            
            await update.message.reply_text(welcome_message)
            context.user_data.clear()
            return ConversationHandler.END
        else:
            # Let user choose role
            keyboard = [
                [
                    InlineKeyboardButton("👨‍👩‍👧‍👦 Family Member", callback_data="role_family"),
                    InlineKeyboardButton("👨‍🍳 Chef", callback_data="role_chef")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Nice to meet you, {name}! 👋\n\n"
                "Please select your role:",
                reply_markup=reply_markup
            )
            
            return States.ROLE
        
    async def select_role(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle role selection."""
        query = update.callback_query
        await query.answer()
        
        role_map = {
            "role_family": UserRole.FAMILY_MEMBER,
            "role_chef": UserRole.CHEF
        }
        
        selected_role = role_map.get(query.data)
        if not selected_role:
            await query.edit_message_text("Invalid selection. Please try again.")
            return States.ROLE
            
        # Create user in database
        async with AsyncSessionLocal() as db:
            user = User(
                id=uuid.uuid4(),
                telegram_id=str(update.effective_user.id),
                name=context.user_data['name'],
                role=selected_role,
                invitation_code=context.user_data['invitation_code']
            )
            
            db.add(user)
            await db.commit()
            
        role_name = selected_role.value.replace('_', ' ').title()
        welcome_message = f"Welcome to ChefLink, {context.user_data['name']}! 🎉\n\n"
        
        if selected_role == UserRole.FAMILY_MEMBER:
            welcome_message += (
                "As a Family Member, I'll help you:\n"
                "• Plan your meals for the week\n"
                "• Track your nutritional goals\n"
                "• Discover new recipes\n\n"
                "Start by typing /plan to create your meal plan!"
            )
        else:
            welcome_message += (
                "As a Chef, you can:\n"
                "• View daily meal plans with /mealplan\n"
                "• Generate shopping lists with /shoppinglist\n\n"
                "Type /help for more information."
            )
            
        await query.edit_message_text(welcome_message)
        
        # Clear user data
        context.user_data.clear()
        
        return ConversationHandler.END
        
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        await update.message.reply_text(
            "Registration cancelled. Type /start to begin again."
        )
        context.user_data.clear()
        return ConversationHandler.END
        
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show help message based on user role."""
        user_id = str(update.effective_user.id)
        
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                await update.message.reply_text(
                    "Please register first using /start command."
                )
                return
                
            if user.role == UserRole.FAMILY_MEMBER:
                help_text = (
                    "🍽️ *Family Member Commands*\n\n"
                    "/plan - Start planning your meals\n"
                    "/myplan - View your current meal plan\n"
                    "/search - Search for recipes\n"
                    "/clear - Clear conversation history\n"
                    "/help - Show this help message\n\n"
                    "You can also chat with me naturally to:\n"
                    "• Modify your meal plan\n"
                    "• Ask for recipe suggestions\n"
                    "• Get nutritional information\n"
                    "• Set dietary preferences\n\n"
                    "I remember our conversation, so feel free to refer back to previous messages!"
                )
            else:
                help_text = (
                    "👨‍🍳 *Chef Commands*\n\n"
                    "/mealplan [date] - Get meal plan for a specific date\n"
                    "/shoppinglist --start=<date> --end=<date> - Generate shopping list\n"
                    "/help - Show this help message\n\n"
                    "Date format: YYYY-MM-DD or 'today', 'tomorrow'"
                )
                
            await update.message.reply_text(help_text, parse_mode='Markdown')