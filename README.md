# Monad Watcher Bot

A Telegram bot that monitors Monad blockchain transfers and sends notifications for large transactions.

## Features

- Real-time monitoring of Monad transfers
- Telegram notifications with transaction details
- Rate limit handling
- Duplicate transaction prevention
- Persistent state management

## Setup

1. Clone the repository:
```bash
git clone https://github.com/heisdaniele/monad-watcher-bot.git
cd monad-watcher-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your configuration:
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=your_channel_id
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_key
```

## Deployment

This bot is designed to be deployed on Render. Follow these steps:

1. Fork this repository
2. Create a new Web Service on Render
3. Connect your GitHub repository
4. Set the following:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot.py`
5. Add your environment variables in Render dashboard

## Environment Variables

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from BotFather
- `TELEGRAM_CHANNEL_ID`: The ID of your Telegram channel
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase service role key