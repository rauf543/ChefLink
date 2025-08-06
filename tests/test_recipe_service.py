import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.schemas.recipe import RecipeSearch
from app.database.models import Recipe
from app.services.recipe_service import RecipeService


@pytest.mark.asyncio
async def test_search_recipes(db_session, sample_recipe):
    """Test recipe search functionality."""
    recipe_service = RecipeService(db_session)
    
    # Search by name
    search_params = RecipeSearch(name="Chicken", limit=10)
    results = await recipe_service.search_recipes(search_params)
    
    assert len(results) == 1
    assert results[0].recipe_name == "Test Chicken Salad"
    
    # Search by calories
    search_params = RecipeSearch(calories_min=300, calories_max=400, limit=10)
    results = await recipe_service.search_recipes(search_params)
    
    assert len(results) == 1
    assert results[0].calories_per_serving == 350
    
    # Search by protein
    search_params = RecipeSearch(main_protein="chicken", limit=10)
    results = await recipe_service.search_recipes(search_params)
    
    assert len(results) == 1
    assert "chicken" in results[0].main_protein


@pytest.mark.asyncio
async def test_check_duplicate(db_session, sample_recipe):
    """Test duplicate recipe detection."""
    recipe_service = RecipeService(db_session)
    
    # Check existing recipe
    is_duplicate = await recipe_service.check_duplicate(
        "Test Chicken Salad",
        "Test Cookbook",
        "Test Author"
    )
    assert is_duplicate is True
    
    # Check non-existing recipe
    is_duplicate = await recipe_service.check_duplicate(
        "New Recipe",
        "New Book",
        "New Author"
    )
    assert is_duplicate is False


@pytest.mark.asyncio
async def test_ingest_single_recipe(db_session, mock_llm_response):
    """Test single recipe ingestion."""
    recipe_service = RecipeService(db_session)
    
    # Mock the LLM service
    with patch.object(recipe_service.llm_service, 'extract_recipe', 
                     return_value=mock_llm_response):
        
        pdf_content = b"mock pdf content"
        recipe = await recipe_service.ingest_single_recipe(pdf_content)
        
        assert recipe.recipe_name == "Test Recipe"
        assert recipe.servings == 4
        assert recipe.calories_per_serving == 300
        assert len(recipe.ingredients) == 2
        assert recipe.ingredients[0] == "1/4 cup ingredient1"


@pytest.mark.asyncio
async def test_ingest_recipe_book(db_session, mock_llm_response):
    """Test recipe book ingestion."""
    recipe_service = RecipeService(db_session)
    
    # Mock TOC extraction
    mock_toc = {
        "Recipe 1": "10-12",
        "Recipe 2": "15"
    }
    
    with patch.object(recipe_service.llm_service, 'extract_table_of_contents',
                     return_value=mock_toc):
        with patch.object(recipe_service.llm_service, 'extract_recipe',
                         return_value=mock_llm_response):
            with patch('app.services.pdf.processor.PDFProcessor.crop_pdf',
                      return_value=b"cropped pdf"):
                
                pdf_content = b"mock recipe book pdf"
                recipes = await recipe_service.ingest_recipe_book(
                    pdf_content, "Test Book"
                )
                
                assert len(recipes) == 2
                assert all(r.recipe_book == "Test Book" for r in recipes)