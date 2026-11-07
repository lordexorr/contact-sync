"""Contact Sync's names and defaults."""
DOMAIN = "contact_sync"
PANEL = "contact-sync"  # the sidebar panel's address, /contact-sync
STATIC_URL = "/contact_sync_static"  # where the panel's files are served from
THUMB_URL = "/api/contact_sync/thumb"
SIGNAL_UPDATED = "contact_sync_updated"  # something the entities show has changed

CONF_CHECK_TIME = "daily_check_time"
CONF_NOTIFY = "notify"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
DEFAULT_CHECK_TIME = "08:00:00"

SUBENTRY_ICLOUD = "icloud"
SUBENTRY_GOOGLE = "google"
