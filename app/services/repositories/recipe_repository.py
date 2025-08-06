"""
Recipe repository implementing clean data access patterns.
Provides optimized queries for recipe operations.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, func, and_, or_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import JSONB

from app.database.models import Recipe
from app.services.repositories.base import CacheableRepository


class RecipeRepository(CacheableRepository[Recipe]):
    """
    Repository for recipe data access with optimized queries.
    Implements caching for frequently accessed recipes.
    """
    
    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session, Recipe, cache_ttl_seconds=600)  # 10 min cache
    
    async def search_recipes(
        self,
        query: Optional[str] = None,
        main_protein: Optional[List[str]] = None,
        max_calories: Optional[int] = None,
        min_protein: Optional[float] = None,
        max_fat: Optional[float] = None,
        recipe_book: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[Recipe]:
        """
        Advanced recipe search with multiple filters.
        Uses database-level filtering for performance.
        
        Args:
            query: Text search query for name/ingredients
            main_protein: List of protein types to filter by
            max_calories: Maximum calories per serving
            min_protein: Minimum protein in grams
            max_fat: Maximum fat in grams
            recipe_book: Filter by recipe book
            limit: Maximum results to return
            offset: Number of results to skip
            
        Returns:
            List of matching recipes
        """
        # Build base query
        stmt = select(Recipe)
        conditions = []
        
        # Text search on name and ingredients
        if query:
            search_pattern = f"%{query}%"
            text_conditions = or_(
                Recipe.recipe_name.ilike(search_pattern),
                cast(Recipe.ingredients, String).ilike(search_pattern)
            )
            conditions.append(text_conditions)
        
        # Protein filter
        if main_protein:
            # Check if any of the requested proteins are in the recipe's protein list
            protein_conditions = []
            for protein in main_protein:
                protein_conditions.append(
                    Recipe.main_protein.contains([protein])
                )
            conditions.append(or_(*protein_conditions))
        
        # Calorie filter
        if max_calories is not None:
            conditions.append(Recipe.calories_per_serving <= max_calories)
        
        # Nutrition filters
        if min_protein is not None:
            # Access JSON field for protein
            conditions.append(
                Recipe.macro_nutrients['protein_g'].astext.cast(Float) >= min_protein
            )
        
        if max_fat is not None:
            conditions.append(
                Recipe.macro_nutrients['fat_g'].astext.cast(Float) <= max_fat
            )
        
        # Recipe book filter
        if recipe_book:
            conditions.append(Recipe.recipe_book == recipe_book)
        
        # Apply conditions
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        # Order by relevance (recipes with more matches first)
        # Then by calories (lower calories first)
        stmt = stmt.order_by(
            Recipe.calories_per_serving.asc(),
            Recipe.recipe_name.asc()
        )
        
        # Apply pagination
        stmt = stmt.offset(offset).limit(limit)
        
        # Execute query
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_recipes_by_ids(self, recipe_ids: List[UUID]) -> Dict[UUID, Recipe]:
        """
        Get multiple recipes by IDs in a single query.
        Returns a dictionary for efficient lookup.
        
        Args:
            recipe_ids: List of recipe UUIDs
            
        Returns:
            Dictionary mapping recipe ID to Recipe object
        """
        if not recipe_ids:
            return {}
        
        stmt = select(Recipe).where(Recipe.id.in_(recipe_ids))
        result = await self.db.execute(stmt)
        recipes = result.scalars().all()
        
        return {recipe.id: recipe for recipe in recipes}
    
    async def get_recipes_by_protein(
        self,
        proteins: List[str],
        limit: int = 20
    ) -> List[Recipe]:
        """
        Get recipes by protein type(s).
        
        Args:
            proteins: List of protein types
            limit: Maximum results
            
        Returns:
            List of recipes with specified proteins
        """
        cache_key = self._cache_key("by_protein", proteins, limit)
        
        async def fetch():
            conditions = []
            for protein in proteins:
                conditions.append(Recipe.main_protein.contains([protein]))
            
            stmt = (
                select(Recipe)
                .where(or_(*conditions))
                .order_by(Recipe.calories_per_serving.asc())
                .limit(limit)
            )
            
            result = await self.db.execute(stmt)
            return result.scalars().all()
        
        return await self.get_cached(cache_key, fetch)
    
    async def get_low_calorie_recipes(
        self,
        max_calories: int = 400,
        limit: int = 20
    ) -> List[Recipe]:
        """
        Get low-calorie recipes.
        
        Args:
            max_calories: Maximum calories per serving
            limit: Maximum results
            
        Returns:
            List of low-calorie recipes
        """
        cache_key = self._cache_key("low_calorie", max_calories, limit)
        
        async def fetch():
            stmt = (
                select(Recipe)
                .where(Recipe.calories_per_serving <= max_calories)
                .order_by(Recipe.calories_per_serving.asc())
                .limit(limit)
            )
            
            result = await self.db.execute(stmt)
            return result.scalars().all()
        
        return await self.get_cached(cache_key, fetch)
    
    async def get_high_protein_recipes(
        self,
        min_protein: float = 30,
        limit: int = 20
    ) -> List[Recipe]:
        """
        Get high-protein recipes.
        
        Args:
            min_protein: Minimum protein in grams
            limit: Maximum results
            
        Returns:
            List of high-protein recipes
        """
        cache_key = self._cache_key("high_protein", min_protein, limit)
        
        async def fetch():
            stmt = (
                select(Recipe)
                .where(
                    Recipe.macro_nutrients['protein_g'].astext.cast(Float) >= min_protein
                )
                .order_by(
                    Recipe.macro_nutrients['protein_g'].astext.cast(Float).desc()
                )
                .limit(limit)
            )
            
            result = await self.db.execute(stmt)
            return result.scalars().all()
        
        return await self.get_cached(cache_key, fetch)
    
    async def get_recipe_books(self) -> List[str]:
        """
        Get list of unique recipe books.
        
        Returns:
            List of recipe book names
        """
        cache_key = self._cache_key("books")
        
        async def fetch():
            stmt = (
                select(Recipe.recipe_book)
                .distinct()
                .where(Recipe.recipe_book.isnot(None))
                .order_by(Recipe.recipe_book)
            )
            
            result = await self.db.execute(stmt)
            return [book for book in result.scalars().all() if book]
        
        return await self.get_cached(cache_key, fetch)
    
    async def get_recipe_stats(self) -> Dict[str, Any]:
        """
        Get aggregate statistics about recipes.
        
        Returns:
            Dictionary with recipe statistics
        """
        cache_key = self._cache_key("stats")
        
        async def fetch():
            # Total count
            count_stmt = select(func.count()).select_from(Recipe)
            count_result = await self.db.execute(count_stmt)
            total_count = count_result.scalar() or 0
            
            # Average calories
            avg_cal_stmt = select(func.avg(Recipe.calories_per_serving))
            avg_cal_result = await self.db.execute(avg_cal_stmt)
            avg_calories = avg_cal_result.scalar() or 0
            
            # Protein distribution
            protein_stmt = (
                select(
                    func.unnest(Recipe.main_protein).label('protein'),
                    func.count().label('count')
                )
                .group_by('protein')
                .order_by(func.count().desc())
            )
            protein_result = await self.db.execute(protein_stmt)
            protein_distribution = {
                row.protein: row.count
                for row in protein_result
            }
            
            return {
                "total_recipes": total_count,
                "average_calories": round(avg_calories, 2),
                "protein_distribution": protein_distribution
            }
        
        return await self.get_cached(cache_key, fetch)