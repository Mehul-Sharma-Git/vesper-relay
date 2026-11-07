# Stockroom

A local move-in supplies tracker for one household. Capture what to buy, filter by
room, and mark purchases. Delivery is a loopback-only web app verified against a
persistent SQLite database. The sample data is synthetic. No deployment or remote
accounts are part of this pilot.

A user can add a name, room, and quantity, retry a submission without duplicates,
filter by room or status, and mark a purchase. An older update cannot overwrite a
newer one. Records remain after the server restarts.
