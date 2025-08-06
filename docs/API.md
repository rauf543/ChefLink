# ChefLink API Documentation

## Base URL
```
http://localhost:8000/api/v1
```

## Authentication
Currently, the API does not require authentication. In production, implement API key or OAuth2.

## Endpoints

### Health Check

#### GET /health
Check if the API is running.

**Response:**
```json
{
  "status": "healthy",
  "service": "ChefLink API"
}
```

### Recipes

#### GET /recipes
List all recipes with pagination.

**Query Parameters:**
- `skip` (int): Number of records to skip (default: 0)
- `limit` (int): Maximum records to return (default: 100)

**Response:**
```json
{
  "recipes": [
    {
      "id": "uuid",
      "recipe_name": "Grilled Chicken Salad",
      "recipe_author": "Chef Name",
      "recipe_book": "Book Title",
      "page_reference": "45",
      "servings": 1,
      "calories_per_serving": 450,
      "macro_nutrients": {
        "protein_g": 35,
        "fat_g": 20,
        "carbohydrates_g": 25
      },
      "main_protein": ["chicken"]
    }
  ],
  "total": 50
}
```

#### POST /recipes/search
Search recipes with filters.

**Request Body:**
```json
{
  "name": "chicken",
  "calories_min": 300,
  "calories_max": 600,
  "protein_min": 25,
  "protein_max": 50,
  "main_protein": "chicken",
  "randomize": false,
  "limit": 10
}
```

**Response:**
```json
{
  "recipes": [...],
  "count": 5
}
```

#### POST /recipes/ingest
Ingest a single recipe from PDF.

**Request Body (multipart/form-data):**
- `file`: PDF file
- `book_title` (optional): Recipe book title
- `page_reference` (optional): Page reference

**Response:**
```json
{
  "success": true,
  "recipe": {
    "id": "uuid",
    "recipe_name": "Recipe Name",
    ...
  }
}
```

### Users

#### GET /users
List all users.

**Query Parameters:**
- `skip` (int): Number of records to skip
- `limit` (int): Maximum records to return
- `role` (string): Filter by role (family_member, chef)

**Response:**
```json
{
  "users": [
    {
      "id": "uuid",
      "name": "User Name",
      "role": "family_member",
      "telegram_id": "123456",
      "created_at": "2024-01-20T10:00:00Z"
    }
  ],
  "total": 10
}
```

### Meal Plans

#### GET /meal-plans
Get meal plans for a user.

**Query Parameters:**
- `user_id` (uuid): User ID
- `start_date` (date): Start date (YYYY-MM-DD)
- `end_date` (date): End date (YYYY-MM-DD)

**Response:**
```json
{
  "meal_plans": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "date": "2024-01-20",
      "meal_type": "breakfast",
      "recipe": {...},
      "status": "unlocked"
    }
  ]
}
```

#### POST /meal-plans
Create a new meal plan entry.

**Request Body:**
```json
{
  "user_id": "uuid",
  "date": "2024-01-20",
  "meal_type": "lunch",
  "recipe_id": "uuid"
}
```

#### PUT /meal-plans/{id}
Update a meal plan entry.

**Request Body:**
```json
{
  "recipe_id": "uuid"
}
```

#### DELETE /meal-plans/{id}
Delete a meal plan entry (only if unlocked).

## Error Responses

All endpoints return consistent error responses:

```json
{
  "detail": "Error message",
  "status_code": 400
}
```

Common status codes:
- 400: Bad Request
- 404: Not Found
- 422: Validation Error
- 500: Internal Server Error

## WebSocket Endpoints

### WS /ws/meal-planning/{user_id}
Real-time meal planning updates (future implementation).

## Rate Limiting

API rate limits (when implemented):
- 100 requests per minute per IP
- 1000 requests per hour per IP

## Webhooks

### Telegram Webhook
POST /telegram/webhook

Used by Telegram to send bot updates. Should be configured with webhook secret.