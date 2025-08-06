import uuid
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas.recipe import RecipeCreate, RecipeSearch
from app.database.models import Recipe
from app.services.llm.factory import get_llm_service
from app.services.nutrition_service import NutritionService
from app.services.pdf.processor import PDFProcessor


class RecipeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm_service = get_llm_service()
        self.nutrition_service = NutritionService()

    async def ingest_single_recipe(
        self, 
        pdf_content: bytes,
        recipe_book: str | None = None,
        page_reference: str | None = None
    ) -> Recipe:
        """Ingest a single recipe from PDF content."""
        # Send PDF directly to LLM for extraction
        recipe_data = await self.llm_service.extract_recipe(pdf_content)
        
        # Override book and page reference if provided
        if recipe_book:
            recipe_data["recipeBook"] = recipe_book
        if page_reference:
            recipe_data["pageReference"] = page_reference
            
        # Check if nutrition info is missing
        if not recipe_data.get("caloriesPerServing") or not recipe_data.get("macroNutrients"):
            # Use nutrition sub-agent
            nutrition_data = await self.nutrition_service.calculate_nutrition(
                recipe_data["ingredients"],
                recipe_data.get("servings", 1)
            )
            recipe_data.update(nutrition_data)
        
        # Check for duplicates
        existing = await self.check_duplicate(
            recipe_data["recipeName"],
            recipe_data.get("recipeBook"),
            recipe_data.get("recipeAuthor")
        )
        
        if existing:
            raise ValueError(f"Recipe already exists: {recipe_data['recipeName']}")
            
        # Create recipe
        recipe = Recipe(
            id=uuid.uuid4(),
            recipe_name=recipe_data["recipeName"],
            recipe_author=recipe_data.get("recipeAuthor"),
            recipe_book=recipe_data.get("recipeBook"),
            page_reference=recipe_data.get("pageReference"),
            servings=recipe_data.get("servings", 1),
            instructions=recipe_data["instructions"],
            ingredients=recipe_data["ingredients"],
            ingredients_original=recipe_data.get("ingredientsOriginal"),
            main_protein=recipe_data["mainProtein"],
            calories_per_serving=recipe_data["caloriesPerServing"],
            macro_nutrients=recipe_data["macroNutrients"]
        )
        
        self.db.add(recipe)
        await self.db.commit()
        await self.db.refresh(recipe)
        
        return recipe

    async def ingest_recipe_book(self, pdf_content: bytes, book_title: str) -> list[Recipe]:
        """Ingest multiple recipes from a recipe book PDF."""
        # Get table of contents from LLM (Claude will analyze first 50 pages automatically)
        toc_data = await self.llm_service.extract_table_of_contents(pdf_content)
        
        recipes = []
        for recipe_name, page_range in toc_data.items():
            # Parse page range
            if '-' in page_range:
                start_page, end_page = page_range.split('-')
                start_page = int(start_page.strip())
                end_page = int(end_page.strip())
            else:
                start_page = end_page = int(page_range.strip())
                
            # Crop PDF to recipe pages
            recipe_pdf = PDFProcessor.crop_pdf(pdf_content, start_page, end_page + 1)
            
            try:
                # Ingest individual recipe
                recipe = await self.ingest_single_recipe(
                    recipe_pdf,
                    recipe_book=book_title,
                    page_reference=page_range
                )
                recipes.append(recipe)
            except Exception as e:
                # Log error but continue with other recipes
                print(f"Failed to ingest {recipe_name}: {str(e)}")
                
        return recipes

    async def check_duplicate(
        self, 
        recipe_name: str, 
        recipe_book: str | None, 
        recipe_author: str | None
    ) -> bool:
        """Check if recipe already exists."""
        query = select(Recipe).where(
            and_(
                Recipe.recipe_name == recipe_name,
                Recipe.recipe_book == recipe_book,
                Recipe.recipe_author == recipe_author
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def search_recipes(self, search_params: RecipeSearch) -> list[Recipe]:
        """Search recipes with filters."""
        query = select(Recipe)
        
        # Apply filters
        if search_params.name:
            query = query.where(Recipe.recipe_name.ilike(f"%{search_params.name}%"))
            
        if search_params.main_protein:
            query = query.where(
                Recipe.main_protein.contains([search_params.main_protein])
            )
            
        if search_params.calories_min is not None:
            query = query.where(Recipe.calories_per_serving >= search_params.calories_min)
            
        if search_params.calories_max is not None:
            query = query.where(Recipe.calories_per_serving <= search_params.calories_max)
            
        if search_params.protein_min is not None:
            query = query.where(
                Recipe.macro_nutrients["protein_g"].astext.cast(int) >= search_params.protein_min
            )
            
        if search_params.protein_max is not None:
            query = query.where(
                Recipe.macro_nutrients["protein_g"].astext.cast(int) <= search_params.protein_max
            )
            
        # Apply randomization if requested
        if search_params.randomize:
            query = query.order_by(func.random())
        else:
            query = query.order_by(Recipe.recipe_name)
            
        # Apply limit
        query = query.limit(search_params.limit)
        
        result = await self.db.execute(query)
        return result.scalars().all()