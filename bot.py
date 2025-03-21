import asyncio
import aiohttp
import ssl
import json
import os
from datetime import datetime, timezone
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from typing import Set

# 1. Initialize Supabase client (use your service_role key to bypass RLS if needed).
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. A small JSON file to persist last polled timestamp across restarts.
STATE_FILE = "state.json"
PROCESSED_TXS_FILE = "processed_txs.json"

def load_state():
    """
    Load the last polled timestamp from a local JSON file.
    If the file doesn't exist or is invalid, return None.
    """
    if not os.path.isfile(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            return data.get("last_polled_time")
    except:
        return None

def save_state(timestamp_str):
    """
    Save the last polled timestamp to the JSON file.
    """
    with open(STATE_FILE, "w") as f:
        json.dump({"last_polled_time": timestamp_str}, f)

def load_processed_txs() -> Set[str]:
    """Load previously processed transaction hashes"""
    if not os.path.isfile(PROCESSED_TXS_FILE):
        return set()
    try:
        with open(PROCESSED_TXS_FILE, 'r') as f:
            return set(json.load(f))
    except:
        return set()

def save_processed_txs(processed_txs: Set[str]) -> None:
    """Save processed transaction hashes"""
    with open(PROCESSED_TXS_FILE, 'w') as f:
        json.dump(list(processed_txs), f)

def escape_markdown(text: str) -> str:
    """
    Escapes reserved characters for MarkdownV2 formatting.
    """
    reserved = r'_*\[\]()~`>#+\-=|{}.!'
    for ch in reserved:
        text = text.replace(ch, f"\\{ch}")
    return text

async def send_telegram_notification(tx_data: dict, retry_after: int = 0) -> None:
    """
    Sends a Telegram notification with rate limit handling
    """
    if retry_after > 0:
        print(f"Rate limited, waiting {retry_after} seconds...")
        await asyncio.sleep(retry_after)
        
    tx_hash = tx_data.get('tx_hash', '')
    from_addr = tx_data.get('from_addr', '')
    to_addr   = tx_data.get('to_addr', '')
    block_num = tx_data.get('block_number', 0)
    amount    = str(tx_data.get('amount', '0')) + " MON"

    # Ensure addresses start with '0x'
    if not tx_hash.startswith('0x'):
        tx_hash = '0x' + tx_hash
    if not from_addr.startswith('0x'):
        from_addr = '0x' + from_addr
    if not to_addr.startswith('0x'):
        to_addr = '0x' + to_addr

    # Escape strings for MarkdownV2
    amount_str = escape_markdown(amount)
    block_str  = escape_markdown(str(block_num))
    from_trunc = escape_markdown(from_addr[:6] + '...' + from_addr[-4:])
    to_trunc   = escape_markdown(to_addr[:6] + '...' + to_addr[-4:])

    # Build Explorer URLs
    base_explorer = "https://testnet.monadexplorer.com"
    tx_url   = f"{base_explorer}/tx/{tx_hash}"
    from_url = f"{base_explorer}/address/{from_addr}"
    to_url   = f"{base_explorer}/address/{to_addr}"
    block_url= f"{base_explorer}/block/{block_num}"

    # Telegram message (MarkdownV2)
    message = (
        "🚨 Large MON Transfer Alert\\!\n\n"
        f"💰 Amount: `{amount_str}`\n"
        f"📦 Block: `{block_str}`\n"
        f"📤 From: `{from_trunc}`\n"
        f"📥 To: `{to_trunc}`\n"
        f"🔍 [View Transaction]({tx_url})"
    )

    # Inline keyboard
    reply_markup = {
        "inline_keyboard": [[
            {"text": "Block",   "url": block_url},
            {"text": "From",    "url": from_url},
            {"text": "To",      "url": to_url},
            {"text": "TxHash",  "url": tx_url}
        ]]
    }

    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": message,
        "parse_mode": "MarkdownV2",
        "reply_markup": reply_markup
    }

    # For dev: SSL context that doesn't verify certificates
    ssl_context = ssl._create_unverified_context()
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.post(telegram_url, json=payload) as resp:
                if resp.status == 200:
                    print(f"✅ Telegram notification sent for tx: {tx_hash}")
                elif resp.status == 429:  # Rate limit
                    error_data = await resp.json()
                    retry_after = error_data.get('parameters', {}).get('retry_after', 30)
                    await send_telegram_notification(tx_data, retry_after)
                else:
                    error_text = await resp.text()
                    print(f"❌ Failed to send Telegram notification: {resp.status} - {error_text}")
        except Exception as exc:
            print("❌ Exception during Telegram notification:", exc)

async def poll_supabase_for_transfers():
    """
    Periodically poll Supabase for new transfers starting from now
    """
    print("🔄 Starting Supabase polling for new transfers...")

    # Load processed transactions
    processed_txs = load_processed_txs()
    
    # Start from current time using timezone-aware datetime
    current_time = datetime.now(timezone.utc).isoformat()
    last_polled_time = current_time
    save_state(current_time)

    while True:
        try:
            query = supabase.table("transfers") \
                .select("*") \
                .gte("created_at", last_polled_time) \
                .order("created_at", desc=False) \
                .limit(10)

            response = query.execute()
            data = response.data
            
            if data:
                print(f"Found {len(data)} transfers to process")
                new_max_time = None
                
                for row in data:
                    tx_hash = row.get('tx_hash', '')
                    
                    # Skip if already processed
                    if tx_hash in processed_txs:
                        print(f"Skipping already processed tx: {tx_hash}")
                        continue

                    # Process new transaction
                    await asyncio.sleep(3)  # Rate limit delay
                    await send_telegram_notification(row)
                    
                    # Mark as processed
                    processed_txs.add(tx_hash)
                    save_processed_txs(processed_txs)

                    # Update last processed time
                    ctime = row.get("created_at")
                    if ctime and (new_max_time is None or ctime > new_max_time):
                        new_max_time = ctime

                if new_max_time:
                    last_polled_time = new_max_time
                    save_state(last_polled_time)

                # Cleanup old transactions if set gets too large
                if len(processed_txs) > 1000:
                    processed_txs = set(list(processed_txs)[-500:])
                    save_processed_txs(processed_txs)

            await asyncio.sleep(10)

        except Exception as e:
            print(f"⚠️ Polling error: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(poll_supabase_for_transfers())
    except KeyboardInterrupt:
        print("\nBot stopped by user. Goodbye!")
