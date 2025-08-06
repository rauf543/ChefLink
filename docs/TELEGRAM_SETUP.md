# Telegram Bot Setup Guide

## Creating Your Telegram Bot

1. **Create a bot with BotFather:**
   - Open Telegram and search for `@BotFather`
   - Send `/newbot`
   - Choose a name for your bot (e.g., "ChefLink Assistant")
   - Choose a username (must end with `bot`, e.g., `cheflink_assistant_bot`)
   - BotFather will give you a token like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

2. **Save your token:**
   - Copy the token to your `.env` file:
   ```
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

## Running Methods

### Method 1: Polling (Recommended for Development)

This is the default method used in the code. The bot actively checks Telegram for new messages.

**Advantages:**
- Works on localhost
- No domain or SSL required
- Easy to debug
- Perfect for development

**Setup:**
1. Leave `TELEGRAM_WEBHOOK_URL` empty in your `.env` file
2. Run the bot: `python bot.py`

### Method 2: Webhooks (For Production)

Telegram sends updates directly to your server. This requires a public HTTPS URL.

**Advantages:**
- More efficient
- Lower latency
- Better for production

**Requirements:**
- Public domain with HTTPS (SSL certificate)
- Open port accessible from internet

**Setup:**
1. Get a public URL (options):
   - **Ngrok (for testing):** 
     ```bash
     ngrok http 8000
     # Copy the HTTPS URL, e.g., https://abc123.ngrok.io
     ```
   - **Production domain:** `https://yourdomain.com`

2. Set webhook URL in `.env`:
   ```
   TELEGRAM_WEBHOOK_URL=https://yourdomain.com/telegram/webhook
   ```

3. The bot will automatically register the webhook when it starts

## Quick Start for Local Development

1. **Get bot token from BotFather** (see above)

2. **Update your `.env` file:**
   ```env
   TELEGRAM_BOT_TOKEN=your_actual_bot_token_here
   TELEGRAM_WEBHOOK_URL=
   ```

3. **Run the bot:**
   ```bash
   python bot.py
   ```

4. **Test your bot:**
   - Open Telegram
   - Search for your bot username
   - Send `/start`

## Production Deployment

For production, you have several options:

### Option 1: Cloud VPS with Domain
1. Deploy to AWS/DigitalOcean/etc.
2. Set up domain and SSL certificate
3. Use webhook URL: `https://yourdomain.com/telegram/webhook`

### Option 2: Heroku
1. Deploy to Heroku
2. Use Heroku app URL: `https://yourapp.herokuapp.com/telegram/webhook`

### Option 3: Cloud Functions
1. Deploy bot as serverless function
2. Use function URL as webhook

### Option 4: Keep Using Polling
- Polling works fine for production too!
- Just ensure your bot service stays running (use systemd, Docker, etc.)

## Troubleshooting

**Bot not responding?**
- Check bot token is correct
- Ensure bot is running (`python bot.py`)
- Check logs for errors

**Webhook issues?**
- URL must be HTTPS (not HTTP)
- Server must be publicly accessible
- Check firewall rules

**For local development:**
- Just use polling (leave TELEGRAM_WEBHOOK_URL empty)
- This is the simplest approach!