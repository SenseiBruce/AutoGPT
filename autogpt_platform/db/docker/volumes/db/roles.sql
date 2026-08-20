-- Passwords are never stored in this file. At container start, psql reads
-- POSTGRES_PASSWORD from the runtime environment / Docker secret and applies it
-- to the role accounts below. Rotate POSTGRES_PASSWORD in your secret store
-- (not in git) if this value was ever exposed.
\set pgpass `echo "$POSTGRES_PASSWORD"`

ALTER USER authenticator WITH PASSWORD :'pgpass';
ALTER USER pgbouncer WITH PASSWORD :'pgpass';
ALTER USER supabase_auth_admin WITH PASSWORD :'pgpass';
ALTER USER supabase_functions_admin WITH PASSWORD :'pgpass';
ALTER USER supabase_storage_admin WITH PASSWORD :'pgpass';
