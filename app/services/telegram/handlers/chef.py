import io
import logging
from datetime import date, datetime, timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from telegram import Update
from telegram.ext import ContextTypes

from app.database.base import AsyncSessionLocal
from app.database.models import MealPlan, Recipe, User
from app.services.telegram.utils import get_user_by_telegram_id, parse_date_range

logger = logging.getLogger(__name__)


class ChefHandlers:
    """Handlers for chef users."""
    
    async def get_daily_meal_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Get meal plan for a specific date."""
        user_id = str(update.effective_user.id)
        
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_id(db, user_id)
            
            if not user or user.role.value != 'chef':
                await update.message.reply_text(
                    "This command is only available for chefs."
                )
                return
                
            # Parse date from command
            args = context.args
            if args and len(args) > 0:
                date_str = args[0].lower()
                if date_str == 'today':
                    target_date = date.today()
                elif date_str == 'tomorrow':
                    target_date = date.today() + timedelta(days=1)
                else:
                    try:
                        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        await update.message.reply_text(
                            "Invalid date format. Use YYYY-MM-DD, 'today', or 'tomorrow'."
                        )
                        return
            else:
                target_date = date.today()
                
            # Get all meal plans for the date
            result = await db.execute(
                select(MealPlan)
                .where(MealPlan.date == target_date)
                .order_by(MealPlan.user_id, MealPlan.meal_type)
                .options(
                    selectinload(MealPlan.recipe),
                    selectinload(MealPlan.user)
                )
            )
            
            meal_plans = result.scalars().all()
            
            if not meal_plans:
                await update.message.reply_text(
                    f"No meal plans found for {target_date.strftime('%B %d, %Y')}."
                )
                return
                
            # Generate PDF report
            pdf_buffer = self._generate_meal_plan_pdf(meal_plans, target_date)
            
            await update.message.reply_document(
                document=pdf_buffer,
                filename=f"meal_plan_{target_date}.pdf",
                caption=f"📅 Meal Plan for {target_date.strftime('%B %d, %Y')}"
            )
            
    async def generate_shopping_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generate shopping list for a date range."""
        user_id = str(update.effective_user.id)
        
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_id(db, user_id)
            
            if not user or user.role.value != 'chef':
                await update.message.reply_text(
                    "This command is only available for chefs."
                )
                return
                
            # Parse date range from command
            # Expected format: /shoppinglist --start=2024-01-20 --end=2024-01-25
            text = update.message.text
            
            # Simple parsing (in production, use proper argument parser)
            start_date = None
            end_date = None
            
            if '--start=' in text and '--end=' in text:
                try:
                    start_idx = text.find('--start=') + 8
                    end_idx = text.find(' ', start_idx)
                    if end_idx == -1:
                        end_idx = len(text)
                    start_str = text[start_idx:end_idx]
                    
                    end_idx = text.find('--end=') + 6
                    end_str = text[end_idx:].strip()
                    
                    start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
                    end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
                except:
                    pass
                    
            if not start_date or not end_date:
                # Default to next 7 days
                start_date = date.today()
                end_date = start_date + timedelta(days=7)
                
            # Get all recipes in date range
            result = await db.execute(
                select(MealPlan)
                .where(MealPlan.date >= start_date)
                .where(MealPlan.date <= end_date)
                .options(selectinload(MealPlan.recipe))
            )
            
            meal_plans = result.scalars().all()
            
            if not meal_plans:
                await update.message.reply_text(
                    f"No meal plans found between {start_date} and {end_date}."
                )
                return
                
            # Aggregate ingredients
            shopping_list = self._aggregate_ingredients(meal_plans)
            
            # Generate PDF shopping list
            pdf_buffer = self._generate_shopping_list_pdf(shopping_list, start_date, end_date)
            pdf_buffer.seek(0)
            
            # Send PDF
            await update.message.reply_document(
                document=pdf_buffer,
                filename=f"shopping_list_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.pdf",
                caption=(
                    f"🛒 *Shopping List*\n"
                    f"📅 {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
                ),
                parse_mode='Markdown'
            )
            
    def _generate_meal_plan_pdf(self, meal_plans: list[MealPlan], target_date: date) -> io.BytesIO:
        """Generate a PDF report of the daily meal plan."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        story = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2C3E50'),
            alignment=1  # Center
        )
        
        story.append(Paragraph(
            f"Meal Plan for {target_date.strftime('%B %d, %Y')}",
            title_style
        ))
        story.append(Spacer(1, 0.5 * inch))
        
        # Group by user
        user_meals = {}
        for plan in meal_plans:
            if plan.user.name not in user_meals:
                user_meals[plan.user.name] = []
            user_meals[plan.user.name].append(plan)
            
        # Create sections for each user
        for user_name, user_plans in user_meals.items():
            # User header
            story.append(Paragraph(f"<b>{user_name}</b>", styles['Heading2']))
            story.append(Spacer(1, 0.2 * inch))
            
            # Meals table
            data = [['Meal', 'Recipe', 'Reference', 'Calories']]
            
            for plan in sorted(user_plans, key=lambda p: p.meal_type.value):
                recipe = plan.recipe
                reference = f"{recipe.recipe_book or ''} p.{recipe.page_reference or ''}"
                data.append([
                    plan.meal_type.value.title(),
                    recipe.recipe_name,
                    reference.strip(),
                    str(recipe.calories_per_serving)
                ])
                
            table = Table(data, colWidths=[1.5 * inch, 3 * inch, 2 * inch, 1 * inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(table)
            story.append(Spacer(1, 0.3 * inch))
            
            # Recipe details
            for plan in sorted(user_plans, key=lambda p: p.meal_type.value):
                recipe = plan.recipe
                story.append(Paragraph(
                    f"<b>{plan.meal_type.value.title()}: {recipe.recipe_name}</b>",
                    styles['Heading3']
                ))
                
                # Ingredients
                story.append(Paragraph("<b>Ingredients:</b>", styles['Normal']))
                for ingredient in recipe.ingredients:
                    story.append(Paragraph(f"• {ingredient}", styles['Normal']))
                    
                story.append(Spacer(1, 0.1 * inch))
                
                # Instructions
                story.append(Paragraph("<b>Instructions:</b>", styles['Normal']))
                story.append(Paragraph(recipe.instructions, styles['Normal']))
                
                story.append(Spacer(1, 0.3 * inch))
                
            story.append(PageBreak())
            
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer
        
    def _aggregate_ingredients(self, meal_plans: list[MealPlan]) -> dict[str, set[str]]:
        """Aggregate ingredients from multiple recipes with intelligent categorization."""
        from collections import defaultdict
        import re
        
        # More comprehensive categorization
        categories = defaultdict(list)
        
        # Enhanced keyword lists for better categorization
        category_keywords = {
            'Produce': {
                'vegetables': ['tomato', 'onion', 'garlic', 'lettuce', 'carrot', 'pepper', 'broccoli', 
                              'spinach', 'kale', 'cabbage', 'cauliflower', 'celery', 'cucumber', 
                              'zucchini', 'mushroom', 'potato', 'sweet potato', 'corn', 'peas'],
                'fruits': ['apple', 'banana', 'orange', 'lemon', 'lime', 'berries', 'strawberry', 
                          'blueberry', 'grape', 'melon', 'pineapple', 'mango', 'peach'],
                'herbs': ['basil', 'parsley', 'cilantro', 'thyme', 'rosemary', 'oregano', 'mint']
            },
            'Proteins': {
                'meat': ['chicken', 'beef', 'pork', 'lamb', 'turkey', 'bacon', 'sausage', 'ham'],
                'seafood': ['fish', 'salmon', 'tuna', 'shrimp', 'prawns', 'crab', 'lobster', 'cod'],
                'plant': ['tofu', 'tempeh', 'beans', 'lentils', 'chickpeas', 'quinoa'],
                'eggs': ['egg', 'eggs']
            },
            'Dairy': {
                'milk': ['milk', 'cream', 'half-and-half', 'buttermilk'],
                'cheese': ['cheese', 'cheddar', 'mozzarella', 'parmesan', 'feta', 'ricotta'],
                'other': ['yogurt', 'butter', 'sour cream', 'cottage cheese']
            },
            'Grains & Bakery': {
                'grains': ['rice', 'pasta', 'noodles', 'couscous', 'barley', 'oats'],
                'bread': ['bread', 'tortilla', 'pita', 'naan', 'bagel', 'croissant'],
                'baking': ['flour', 'yeast', 'baking powder', 'baking soda']
            },
            'Pantry Staples': {
                'oils': ['oil', 'olive oil', 'vegetable oil', 'coconut oil', 'sesame oil'],
                'condiments': ['ketchup', 'mustard', 'mayonnaise', 'vinegar', 'soy sauce', 'hot sauce'],
                'spices': ['salt', 'pepper', 'paprika', 'cumin', 'coriander', 'turmeric', 'cinnamon'],
                'sweeteners': ['sugar', 'honey', 'maple syrup', 'agave'],
                'canned': ['canned', 'tomato sauce', 'tomato paste', 'broth', 'stock']
            },
            'Frozen': {
                'frozen': ['frozen', 'ice cream', 'frozen vegetables', 'frozen fruit']
            }
        }
        
        # Aggregate ingredients with quantities
        ingredient_map = defaultdict(list)
        
        for plan in meal_plans:
            for ingredient in plan.recipe.ingredients:
                # Try to parse quantity and item
                # Simple regex to extract number and unit
                match = re.match(r'^([\d./\s]+)?\s*(\w+)?\s*(.+)$', ingredient)
                if match:
                    quantity = match.group(1) or ""
                    unit = match.group(2) or ""
                    item = match.group(3) or ingredient
                else:
                    item = ingredient
                
                # Normalize the item name for matching
                item_lower = item.lower().strip()
                
                # Find the best category
                categorized = False
                for main_category, subcategories in category_keywords.items():
                    for subcat, keywords in subcategories.items():
                        if any(keyword in item_lower for keyword in keywords):
                            # Add the original ingredient to preserve quantities
                            categories[main_category].append(ingredient)
                            categorized = True
                            break
                    if categorized:
                        break
                
                if not categorized:
                    categories['Other'].append(ingredient)
        
        # Convert lists to sets to remove exact duplicates
        # In a more advanced version, we'd merge similar ingredients
        final_categories = {}
        for category, ingredients in categories.items():
            if ingredients:
                # Remove duplicates while preserving order
                seen = set()
                unique_ingredients = []
                for ing in ingredients:
                    if ing not in seen:
                        seen.add(ing)
                        unique_ingredients.append(ing)
                final_categories[category] = unique_ingredients
        
        return final_categories
    
    def _generate_shopping_list_pdf(self, shopping_list: dict[str, list[str]], start_date: date, end_date: date) -> io.BytesIO:
        """Generate a PDF shopping list organized by category."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        story = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2C3E50'),
            alignment=1  # Center
        )
        
        story.append(Paragraph(
            f"Shopping List",
            title_style
        ))
        story.append(Paragraph(
            f"{start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}",
            styles['Normal']
        ))
        story.append(Spacer(1, 0.5 * inch))
        
        # Category order for better shopping flow
        category_order = [
            'Produce', 
            'Proteins', 
            'Dairy', 
            'Grains & Bakery',
            'Pantry Staples',
            'Frozen',
            'Other'
        ]
        
        # Create sections for each category
        for category in category_order:
            if category in shopping_list and shopping_list[category]:
                # Category header
                story.append(Paragraph(f"<b>{category}</b>", styles['Heading2']))
                story.append(Spacer(1, 0.1 * inch))
                
                # Create a table for checklist format
                data = []
                for ingredient in shopping_list[category]:
                    # Add checkbox symbol and ingredient
                    data.append(['☐', ingredient])
                
                # Create table with checkbox column
                table = Table(data, colWidths=[0.3 * inch, 6.5 * inch])
                table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ('FONTSIZE', (0, 0), (-1, -1), 11),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('LEFTPADDING', (0, 0), (0, -1), 0),
                    ('RIGHTPADDING', (0, 0), (0, -1), 5),
                ]))
                
                story.append(table)
                story.append(Spacer(1, 0.3 * inch))
        
        # Add notes section
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph("<b>Notes:</b>", styles['Heading3']))
        story.append(Spacer(1, 0.1 * inch))
        
        # Add lines for notes
        for _ in range(5):
            story.append(Paragraph("_" * 80, styles['Normal']))
            story.append(Spacer(1, 0.2 * inch))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer