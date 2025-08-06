# ChefLink Deployment Guide

## Prerequisites

- Docker and Docker Compose
- PostgreSQL (for production)
- Redis (for Celery task queue)
- Valid Telegram Bot Token
- Anthropic API Key (for Claude Opus 4)

## Local Development

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd cheflink
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   make install
   ```

4. **Run with Docker Compose:**
   ```bash
   make docker-up
   ```

   This starts:
   - PostgreSQL database
   - Redis cache
   - API server (port 8000)
   - Telegram bot
   - Celery worker

5. **Initialize sample data:**
   ```bash
   python scripts/init_db.py
   ```

## Production Deployment

### Using Docker

1. **Build production images:**
   ```bash
   docker build -t cheflink-api:latest .
   docker build -t cheflink-bot:latest -f Dockerfile.bot .
   ```

2. **Environment variables for production:**
   - Use strong passwords for database
   - Set `APP_ENV=production`
   - Set `DEBUG=False`
   - Use proper SECRET_KEY

3. **Database setup:**
   ```bash
   # Run migrations
   docker run --env-file .env cheflink-api:latest alembic upgrade head
   ```

4. **Run services:**
   ```bash
   # API Server
   docker run -d \
     --name cheflink-api \
     --env-file .env \
     -p 8000:8000 \
     cheflink-api:latest

   # Telegram Bot
   docker run -d \
     --name cheflink-bot \
     --env-file .env \
     --restart unless-stopped \
     cheflink-bot:latest
   ```

### Using Kubernetes

See `k8s/` directory for Kubernetes manifests (if implemented).

### Cloud Deployment Options

#### AWS
1. Use ECS for container orchestration
2. RDS for PostgreSQL
3. ElastiCache for Redis
4. ALB for load balancing

#### Google Cloud
1. Use Cloud Run for containers
2. Cloud SQL for PostgreSQL
3. Memorystore for Redis

#### Heroku
1. Use Heroku Postgres
2. Heroku Redis
3. Deploy using Heroku Container Registry

## Monitoring

1. **Health checks:**
   - API: `GET /api/v1/health`
   - Bot: Monitor Telegram webhook status

2. **Logging:**
   - Application logs to stdout
   - Use log aggregation service (ELK, CloudWatch, etc.)

3. **Metrics:**
   - Monitor API response times
   - Track recipe ingestion success rate
   - Monitor bot response times

## Backup Strategy

1. **Database backups:**
   ```bash
   pg_dump -h localhost -U cheflink -d cheflink > backup_$(date +%Y%m%d).sql
   ```

2. **Automated backups:**
   - Set up daily automated backups
   - Store in S3 or similar object storage
   - Test restore procedures regularly

## Security Considerations

1. **API Security:**
   - Use HTTPS in production
   - Implement rate limiting
   - Add API authentication if needed

2. **Bot Security:**
   - Validate all user inputs
   - Use webhook secret for Telegram
   - Implement user rate limiting

3. **Database Security:**
   - Use SSL connections
   - Implement proper access controls
   - Regular security updates

## Scaling

1. **Horizontal scaling:**
   - API can be scaled horizontally
   - Use load balancer for multiple instances
   - Ensure session persistence

2. **Database scaling:**
   - Use read replicas for queries
   - Consider partitioning for large datasets
   - Implement caching strategy

3. **Bot scaling:**
   - Use webhook mode for better performance
   - Implement queue for long-running tasks
   - Consider sharding for many users