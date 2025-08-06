import asyncio
import uuid
from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import Recipe, User, UserRole


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    """Create a test database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    yield engine
    
    await engine.dispose()


@pytest.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def sample_recipe(db_session: AsyncSession) -> Recipe:
    """Create a sample recipe for testing."""
    recipe = Recipe(
        id=uuid.uuid4(),
        recipe_name="Test Chicken Salad",
        recipe_author="Test Author",
        recipe_book="Test Cookbook",
        page_reference="42",
        servings=1,
        instructions="Mix all ingredients together.",
        ingredients=["1/4 chicken breast", "1 cup lettuce", "2 tbsp dressing"],
        ingredients_original=["1 chicken breast (serves 4)", "4 cups lettuce", "8 tbsp dressing"],
        main_protein=["chicken"],
        calories_per_serving=350,
        macro_nutrients={
            "protein_g": 30,
            "fat_g": 15,
            "carbohydrates_g": 20
        }
    )
    
    db_session.add(recipe)
    await db_session.commit()
    await db_session.refresh(recipe)
    
    return recipe


@pytest.fixture
async def sample_user(db_session: AsyncSession) -> User:
    """Create a sample user for testing."""
    user = User(
        id=uuid.uuid4(),
        telegram_id="123456789",
        name="Test User",
        role=UserRole.FAMILY_MEMBER,
        invitation_code="TEST1234"
    )
    
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    return user


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing."""
    return {
        "recipeName": "Test Recipe",
        "recipeAuthor": "Test Author",
        "recipeBook": None,
        "pageReference": None,
        "servings": 4,
        "instructions": "Test instructions",
        "ingredients": ["1/4 cup ingredient1", "1/2 tbsp ingredient2"],
        "ingredientsOriginal": ["1 cup ingredient1", "2 tbsp ingredient2"],
        "mainProtein": ["chicken"],
        "caloriesPerServing": 300,
        "macroNutrients": {
            "protein_g": 25,
            "fat_g": 10,
            "carbohydrates_g": 30
        }
    }