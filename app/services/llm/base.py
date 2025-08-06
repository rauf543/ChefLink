from abc import ABC, abstractmethod
from typing import Any


class BaseLLMService(ABC):
    @abstractmethod
    async def extract_recipe(self, pdf_content: bytes) -> dict[str, Any]:
        """Extract recipe data from PDF content."""
        pass

    @abstractmethod
    async def extract_table_of_contents(self, pdf_content: bytes) -> dict[str, str]:
        """Extract table of contents from recipe book PDF."""
        pass

    @abstractmethod
    async def calculate_nutrition(self, ingredients: list[str], servings: int) -> dict[str, Any]:
        """Calculate nutrition information for ingredients."""
        pass