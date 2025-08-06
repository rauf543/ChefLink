"""
Centralized tool registry to eliminate duplication between handlers.
Provides a single source of truth for tool definitions and execution.
"""
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """Categorizes tools by their functional domain"""
    MEAL_PLANNING = "meal_planning"
    RECIPE_SEARCH = "recipe_search"
    NUTRITION = "nutrition"
    USER_PREFERENCES = "user_preferences"


@dataclass
class ToolParameter:
    """Defines a single parameter for a tool"""
    name: str
    type: str
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    default: Any = None


@dataclass
class Tool:
    """Represents a single tool with its metadata and execution logic"""
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter]
    executor: Optional[Callable] = None
    
    def to_anthropic_schema(self) -> Dict:
        """Convert to Anthropic Claude tool schema format"""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop_def = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop_def["enum"] = param.enum
            
            properties[param.name] = prop_def
            
            if param.required:
                required.append(param.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    
    def to_openai_schema(self) -> Dict:
        """Convert to OpenAI function calling format"""
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        for param in self.parameters:
            prop_def = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop_def["enum"] = param.enum
            
            parameters["properties"][param.name] = prop_def
            
            if param.required:
                parameters["required"].append(param.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": parameters
        }


class ToolRegistry:
    """
    Central registry for all tools in the system.
    Eliminates duplication and provides consistent tool definitions.
    """
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._initialize_tools()
    
    def _initialize_tools(self):
        """Initialize all available tools"""
        # Meal Planning Tools
        self.register(Tool(
            name="create_meal_plan",
            description="Create a new meal plan for the user",
            category=ToolCategory.MEAL_PLANNING,
            parameters=[
                ToolParameter(
                    name="date",
                    type="string",
                    description="Date for the meal plan (YYYY-MM-DD format)"
                ),
                ToolParameter(
                    name="meals",
                    type="array",
                    description="List of meals with recipe_id, meal_type, and servings"
                )
            ]
        ))
        
        self.register(Tool(
            name="update_meal_plan",
            description="Update an existing meal plan",
            category=ToolCategory.MEAL_PLANNING,
            parameters=[
                ToolParameter(
                    name="date",
                    type="string",
                    description="Date of the meal plan to update (YYYY-MM-DD format)"
                ),
                ToolParameter(
                    name="meal_type",
                    type="string",
                    description="Type of meal to update",
                    enum=["breakfast", "lunch", "dinner", "snack"]
                ),
                ToolParameter(
                    name="recipe_id",
                    type="string",
                    description="ID of the new recipe"
                ),
                ToolParameter(
                    name="servings",
                    type="integer",
                    description="Number of servings",
                    default=1
                )
            ]
        ))
        
        self.register(Tool(
            name="get_meal_plans",
            description="Retrieve user's meal plans for a date range",
            category=ToolCategory.MEAL_PLANNING,
            parameters=[
                ToolParameter(
                    name="start_date",
                    type="string",
                    description="Start date (YYYY-MM-DD format)",
                    required=False
                ),
                ToolParameter(
                    name="end_date",
                    type="string",
                    description="End date (YYYY-MM-DD format)",
                    required=False
                ),
                ToolParameter(
                    name="days",
                    type="integer",
                    description="Number of days to retrieve",
                    required=False,
                    default=7
                )
            ]
        ))
        
        # Recipe Search Tools
        self.register(Tool(
            name="search_recipes",
            description="Search for recipes based on various criteria",
            category=ToolCategory.RECIPE_SEARCH,
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="Search query for recipe names or ingredients",
                    required=False
                ),
                ToolParameter(
                    name="main_protein",
                    type="array",
                    description="Filter by main protein types",
                    required=False
                ),
                ToolParameter(
                    name="max_calories",
                    type="integer",
                    description="Maximum calories per serving",
                    required=False
                ),
                ToolParameter(
                    name="min_protein",
                    type="number",
                    description="Minimum protein in grams",
                    required=False
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of results",
                    required=False,
                    default=10
                )
            ]
        ))
        
        self.register(Tool(
            name="get_recipe_details",
            description="Get detailed information about a specific recipe",
            category=ToolCategory.RECIPE_SEARCH,
            parameters=[
                ToolParameter(
                    name="recipe_id",
                    type="string",
                    description="The unique ID of the recipe"
                )
            ]
        ))
        
        # Nutrition Tools
        self.register(Tool(
            name="analyze_nutrition",
            description="Analyze nutritional content of a meal or day",
            category=ToolCategory.NUTRITION,
            parameters=[
                ToolParameter(
                    name="date",
                    type="string",
                    description="Date to analyze (YYYY-MM-DD format)"
                ),
                ToolParameter(
                    name="meal_type",
                    type="string",
                    description="Specific meal to analyze",
                    required=False,
                    enum=["breakfast", "lunch", "dinner", "snack", "all"]
                )
            ]
        ))
        
        # User Preference Tools
        self.register(Tool(
            name="update_dietary_preferences",
            description="Update user's dietary preferences and restrictions",
            category=ToolCategory.USER_PREFERENCES,
            parameters=[
                ToolParameter(
                    name="preferences",
                    type="object",
                    description="Dictionary of dietary preferences"
                )
            ]
        ))
        
        self.register(Tool(
            name="get_user_preferences",
            description="Retrieve user's current dietary preferences",
            category=ToolCategory.USER_PREFERENCES,
            parameters=[]
        ))
    
    def register(self, tool: Tool) -> None:
        """Register a new tool"""
        if tool.name in self._tools:
            logger.warning(f"Tool {tool.name} already registered, overwriting")
        self._tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a specific tool by name"""
        return self._tools.get(name)
    
    def get_tools_by_category(self, category: ToolCategory) -> List[Tool]:
        """Get all tools in a specific category"""
        return [tool for tool in self._tools.values() if tool.category == category]
    
    def get_all_tools(self) -> List[Tool]:
        """Get all registered tools"""
        return list(self._tools.values())
    
    def get_tool_schemas(self, provider: str = "anthropic") -> List[Dict]:
        """
        Get tool schemas formatted for specific LLM provider
        
        Args:
            provider: "anthropic" or "openai"
        """
        tools = []
        for tool in self._tools.values():
            if provider == "anthropic":
                tools.append(tool.to_anthropic_schema())
            elif provider == "openai":
                tools.append(tool.to_openai_schema())
            else:
                raise ValueError(f"Unknown provider: {provider}")
        
        return tools
    
    def attach_executor(self, tool_name: str, executor: Callable) -> None:
        """
        Attach an executor function to a tool
        
        Args:
            tool_name: Name of the tool
            executor: Async function that executes the tool
        """
        tool = self.get_tool(tool_name)
        if tool:
            tool.executor = executor
        else:
            raise ValueError(f"Tool {tool_name} not found")


# Singleton instance
_registry = None

def get_tool_registry() -> ToolRegistry:
    """Get the singleton tool registry instance"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry