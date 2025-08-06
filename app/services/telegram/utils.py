import random
import string
from enum import IntEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User


class States(IntEnum):
    """Conversation states for the bot."""
    INVITATION_CODE = 1
    NAME = 2
    ROLE = 3
    MEAL_PLANNING_DURATION = 4
    MEAL_PLANNING_GOALS = 5
    MEAL_PLANNING_HABITS = 6
    MEAL_PLANNING_CONFIRM = 7


def generate_invitation_code(length: int = 8) -> str:
    """Generate a random invitation code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


async def get_user_by_telegram_id(db: AsyncSession, telegram_id: str) -> User | None:
    """Get user by Telegram ID."""
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


def format_meal_plan_summary(meal_plans: list) -> str:
    """Format meal plans into a readable summary."""
    if not meal_plans:
        return "No meal plans scheduled."
        
    summary = []
    current_date = None
    
    for plan in meal_plans:
        if plan.date != current_date:
            if current_date:
                summary.append("")  # Add blank line between days
            summary.append(f"📅 *{plan.date.strftime('%A, %B %d')}*")
            current_date = plan.date
            
        status_emoji = "🔒" if plan.status.value == "locked" else "🔓"
        summary.append(
            f"{status_emoji} *{plan.meal_type.value.title()}:* {plan.recipe.recipe_name} "
            f"({plan.recipe.calories_per_serving} cal)"
        )
        
    return "\n".join(summary)


def parse_date_range(date_str: str) -> tuple[str, str] | None:
    """Parse date range from string like 'tomorrow-friday' or '2024-01-20--2024-01-25'."""
    from datetime import datetime, timedelta
    
    parts = date_str.lower().split('-')
    if len(parts) != 2:
        return None
        
    # Map day names to dates
    day_mapping = {
        'today': datetime.now().date(),
        'tomorrow': datetime.now().date() + timedelta(days=1),
        'monday': get_next_weekday(0),
        'tuesday': get_next_weekday(1),
        'wednesday': get_next_weekday(2),
        'thursday': get_next_weekday(3),
        'friday': get_next_weekday(4),
        'saturday': get_next_weekday(5),
        'sunday': get_next_weekday(6),
    }
    
    # Try to parse start date
    start = None
    if parts[0] in day_mapping:
        start = day_mapping[parts[0]]
    else:
        try:
            start = datetime.strptime(parts[0], '%Y-%m-%d').date()
        except ValueError:
            return None
            
    # Try to parse end date
    end = None
    if parts[1] in day_mapping:
        end = day_mapping[parts[1]]
    else:
        try:
            end = datetime.strptime(parts[1], '%Y-%m-%d').date()
        except ValueError:
            return None
            
    if start and end and start <= end:
        return str(start), str(end)
        
    return None


def get_next_weekday(weekday: int):
    """Get the next occurrence of a weekday (0=Monday, 6=Sunday)."""
    from datetime import datetime, timedelta
    
    today = datetime.now().date()
    days_ahead = weekday - today.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return today + timedelta(days_ahead)