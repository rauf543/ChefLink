"""
Base repository pattern implementation for clean data access layer.
Provides common CRUD operations and query patterns.
"""
from typing import TypeVar, Generic, Type, Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.database.base import Base

# Generic type for models
ModelType = TypeVar('ModelType', bound=Base)


class BaseRepository(Generic[ModelType], ABC):
    """
    Abstract base repository providing common database operations.
    Implements repository pattern for clean separation of data access.
    """
    
    def __init__(self, db_session: AsyncSession, model: Type[ModelType]):
        self.db = db_session
        self.model = model
    
    async def get_by_id(self, entity_id: UUID) -> Optional[ModelType]:
        """
        Get entity by ID.
        
        Args:
            entity_id: Entity UUID
            
        Returns:
            Entity or None if not found
        """
        query = select(self.model).where(self.model.id == entity_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelType]:
        """
        Get all entities with optional filtering and pagination.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            filters: Optional filter criteria
            
        Returns:
            List of entities
        """
        query = select(self.model)
        
        # Apply filters
        if filters:
            conditions = []
            for key, value in filters.items():
                if hasattr(self.model, key):
                    conditions.append(getattr(self.model, key) == value)
            if conditions:
                query = query.where(and_(*conditions))
        
        # Apply pagination
        query = query.offset(skip).limit(limit)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def create(self, entity: ModelType) -> ModelType:
        """
        Create a new entity.
        
        Args:
            entity: Entity to create
            
        Returns:
            Created entity
        """
        self.db.add(entity)
        await self.db.commit()
        await self.db.refresh(entity)
        return entity
    
    async def create_batch(self, entities: List[ModelType]) -> List[ModelType]:
        """
        Create multiple entities in a single transaction.
        
        Args:
            entities: List of entities to create
            
        Returns:
            List of created entities
        """
        self.db.add_all(entities)
        await self.db.commit()
        
        # Refresh all entities
        for entity in entities:
            await self.db.refresh(entity)
        
        return entities
    
    async def update(self, entity_id: UUID, updates: Dict[str, Any]) -> Optional[ModelType]:
        """
        Update an entity by ID.
        
        Args:
            entity_id: Entity UUID
            updates: Dictionary of updates
            
        Returns:
            Updated entity or None if not found
        """
        entity = await self.get_by_id(entity_id)
        if not entity:
            return None
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        
        # Update timestamp if model has it
        if hasattr(entity, 'updated_at'):
            entity.updated_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(entity)
        return entity
    
    async def delete(self, entity_id: UUID) -> bool:
        """
        Delete an entity by ID.
        
        Args:
            entity_id: Entity UUID
            
        Returns:
            True if deleted, False if not found
        """
        entity = await self.get_by_id(entity_id)
        if not entity:
            return False
        
        await self.db.delete(entity)
        await self.db.commit()
        return True
    
    async def exists(self, entity_id: UUID) -> bool:
        """
        Check if entity exists.
        
        Args:
            entity_id: Entity UUID
            
        Returns:
            True if exists, False otherwise
        """
        query = select(func.count()).where(self.model.id == entity_id)
        result = await self.db.execute(query)
        count = result.scalar()
        return count > 0
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count entities with optional filtering.
        
        Args:
            filters: Optional filter criteria
            
        Returns:
            Count of entities
        """
        query = select(func.count()).select_from(self.model)
        
        # Apply filters
        if filters:
            conditions = []
            for key, value in filters.items():
                if hasattr(self.model, key):
                    conditions.append(getattr(self.model, key) == value)
            if conditions:
                query = query.where(and_(*conditions))
        
        result = await self.db.execute(query)
        return result.scalar() or 0


class CacheableRepository(BaseRepository[ModelType]):
    """
    Repository with caching capabilities for frequently accessed data.
    Implements simple in-memory caching with TTL.
    """
    
    def __init__(
        self,
        db_session: AsyncSession,
        model: Type[ModelType],
        cache_ttl_seconds: int = 300
    ):
        super().__init__(db_session, model)
        self.cache: Dict[str, Tuple[Any, datetime]] = {}
        self.cache_ttl_seconds = cache_ttl_seconds
    
    def _cache_key(self, method: str, *args, **kwargs) -> str:
        """Generate cache key from method and arguments"""
        key_parts = [method]
        key_parts.extend(str(arg) for arg in args)
        key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
        return ":".join(key_parts)
    
    def _is_cache_valid(self, cached_at: datetime) -> bool:
        """Check if cached data is still valid"""
        age = (datetime.utcnow() - cached_at).total_seconds()
        return age < self.cache_ttl_seconds
    
    async def get_cached(
        self,
        cache_key: str,
        fetch_func,
        *args,
        **kwargs
    ) -> Any:
        """
        Get data from cache or fetch if not cached.
        
        Args:
            cache_key: Cache key
            fetch_func: Function to fetch data if not cached
            *args, **kwargs: Arguments for fetch function
            
        Returns:
            Cached or fetched data
        """
        # Check cache
        if cache_key in self.cache:
            data, cached_at = self.cache[cache_key]
            if self._is_cache_valid(cached_at):
                return data
        
        # Fetch fresh data
        data = await fetch_func(*args, **kwargs)
        
        # Update cache
        self.cache[cache_key] = (data, datetime.utcnow())
        
        return data
    
    def invalidate_cache(self, pattern: Optional[str] = None) -> None:
        """
        Invalidate cache entries.
        
        Args:
            pattern: Optional pattern to match cache keys
        """
        if pattern:
            keys_to_remove = [
                key for key in self.cache.keys()
                if pattern in key
            ]
            for key in keys_to_remove:
                del self.cache[key]
        else:
            self.cache.clear()