CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_users (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 email text NOT NULL,
 password_hash text NOT NULL,
 display_name varchar(60) NOT NULL,
 is_active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 last_login_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_app_users_email_lower ON app_users(lower(email));

CREATE TABLE IF NOT EXISTS user_profiles (
 user_id uuid PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
 gender varchar(20), age integer CHECK(age BETWEEN 1 AND 120),
 height_cm numeric(6,2), weight_kg numeric(6,2),
 dialysis_type varchar(30) NOT NULL DEFAULT '혈액투석',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS auth_sessions (
 id bigserial PRIMARY KEY, user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 token_hash char(64) NOT NULL UNIQUE, expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_expiry ON auth_sessions(expires_at);

CREATE TABLE IF NOT EXISTS meal_records (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 title text NOT NULL, subtitle text, payload jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS favorites (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 title text NOT NULL, subtitle text, payload jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS user_documents (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 title text NOT NULL, subtitle text, payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 storage_key text, mime_type text DEFAULT 'application/pdf', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS shopping_cart_items (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 name text NOT NULL, amount numeric(10,2), unit varchar(20) DEFAULT 'g', checked boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_meal_records_user_created ON meal_records(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS ix_favorites_user_created ON favorites(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS ix_documents_user_created ON user_documents(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS ix_cart_user ON shopping_cart_items(user_id);
