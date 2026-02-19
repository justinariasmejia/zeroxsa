import aiosqlite
import os

# Base directory for databases
DB_DIR = os.path.dirname(os.path.abspath(__file__))

def get_db_path(guild_id):
    """Returns the absolute path to the database for a specific guild."""
    return os.path.join(DB_DIR, f"letters_{guild_id}.db")

async def init_db(guild_ids):
    """Initializes the database tables for the specified list of guild IDs."""
    for guild_id in guild_ids:
        db_path = get_db_path(guild_id)
        print(f"🛠️ Initializing database for Guild {guild_id} at {db_path}...")
        
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER,
                    sender_name TEXT,
                    recipient TEXT,
                    message TEXT,
                    is_anonymous BOOLEAN,
                    timestamp DATETIME
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS birthdays (
                    user_id INTEGER PRIMARY KEY,
                    day INTEGER,
                    month INTEGER,
                    year INTEGER
                )
            """)
            await db.commit()

def load_server_config():
    """Loads per-server configuration from environment variables."""
    from dotenv import load_dotenv
    load_dotenv()
    
    config = {}
    
    # helper to clean IDs
    def clean_id(val):
        if not val: return None
        try: return int(val.strip())
        except: return None

    # helper to clean ID lists
    def clean_id_list(val):
        if not val: return []
        val = str(val)
        return [int(x.strip()) for x in val.split(',') if x.strip().isdigit()]

    # helper for booleans (default True)
    def clean_bool(val):
        if val is None: return True
        return val.lower() in ('true', '1', 'yes', 'on')

    # ZEROP
    zerop_id = clean_id(os.getenv('ZEROP_GUILD_ID'))
    if zerop_id:
        config[zerop_id] = {
            'token': os.getenv('ZEROP_TOKEN'),
            'log_token': os.getenv('ZEROP_LOG_TOKEN'),
            'birthday_channel_id': clean_id(os.getenv('ZEROP_BIRTHDAY_CHANNEL_ID')),
            'ticket_support_role_id': clean_id_list(os.getenv('ZEROP_TICKET_SUPPORT_ROLE_ID')),
            'ticket_log_channel_id': clean_id(os.getenv('ZEROP_TICKET_LOG_CHANNEL_ID')),
            'admin_ids': clean_id_list(os.getenv('ZEROP_ADMIN_USER_ID')),
            'log_recipients': clean_id_list(os.getenv('ZEROP_LOG_RECIPIENTS')),
            # Feature Flags
            'enable_letters': clean_bool(os.getenv('ZEROP_ENABLE_LETTERS')),
            'enable_tickets': clean_bool(os.getenv('ZEROP_ENABLE_TICKETS')),
            'enable_birthdays': clean_bool(os.getenv('ZEROP_ENABLE_BIRTHDAYS'))
        }

    # IGLESIA
    iglesia_id = clean_id(os.getenv('IGLESIA_GUILD_ID'))
    if iglesia_id:
        config[iglesia_id] = {
            'token': os.getenv('IGLESIA_TOKEN'),
            'log_token': os.getenv('IGLESIA_LOG_TOKEN'),
            'birthday_channel_id': clean_id(os.getenv('IGLESIA_BIRTHDAY_CHANNEL_ID')),
            'ticket_support_role_id': clean_id_list(os.getenv('IGLESIA_TICKET_SUPPORT_ROLE_ID')),
            'ticket_log_channel_id': clean_id(os.getenv('IGLESIA_TICKET_LOG_CHANNEL_ID')),
            'admin_ids': clean_id_list(os.getenv('IGLESIA_ADMIN_USER_ID')),
            'log_recipients': clean_id_list(os.getenv('IGLESIA_LOG_RECIPIENTS')),
            # Feature Flags
            'enable_letters': clean_bool(os.getenv('IGLESIA_ENABLE_LETTERS')),
            'enable_tickets': clean_bool(os.getenv('IGLESIA_ENABLE_TICKETS')),
            'enable_birthdays': clean_bool(os.getenv('IGLESIA_ENABLE_BIRTHDAYS'))
        }
        
    return config
