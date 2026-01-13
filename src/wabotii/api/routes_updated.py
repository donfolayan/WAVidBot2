"""Updated webhook handler for WAHA format."""

# The webhook handler needs to be updated to handle WAHA's payload format.
# WAHA sends webhooks in this structure:
# {
#   "event": "message",
#   "session": "default",
#   "payload": {
#     "id": "message_id",
#     "from": "1234567890@c.us",
#     "body": "message text",
#     ...
#   }
# }

# The current code expects:
# {
#   "data": {
#     "messages": [{
#       "id": "...",
#       "from": "...",
#       "text": {"body": "..."}
#     }]
#   }
# }

# We need to update the webhook handler to support both formats
