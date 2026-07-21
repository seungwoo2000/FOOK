BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  password_hash text NOT NULL,
  display_name varchar(80) NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','withdrawn')),
  email_verified_at timestamptz,
  last_login_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT app_users_email_normalized CHECK (email = lower(trim(email)))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_app_users_email ON app_users (lower(email));

CREATE TABLE IF NOT EXISTS user_profiles (
  user_id uuid PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
  gender varchar(20),
  birth_year smallint CHECK (birth_year BETWEEN 1900 AND EXTRACT(YEAR FROM now())::int),
  height_cm numeric(5,1) CHECK (height_cm BETWEEN 80 AND 250),
  weight_kg numeric(5,1) CHECK (weight_kg BETWEEN 20 AND 300),
  dialysis_type varchar(30) NOT NULL DEFAULT 'hemodialysis' CHECK (dialysis_type IN ('hemodialysis','peritoneal')),
  dialysis_days smallint[] DEFAULT '{}',
  allergies text[] NOT NULL DEFAULT '{}',
  disliked_ingredients text[] NOT NULL DEFAULT '{}',
  target_notes text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meal_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  source varchar(30) NOT NULL DEFAULT 'generated' CHECK (source IN ('generated','manual','imported')),
  meal_type varchar(20) CHECK (meal_type IN ('breakfast','lunch','dinner','snack','other')),
  title text NOT NULL,
  meal_payload jsonb NOT NULL,
  nutrition_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  target_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  consumed_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  eaten_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_meal_records_user_created ON meal_records(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_meal_records_payload_gin ON meal_records USING gin(meal_payload);

CREATE TABLE IF NOT EXISTS favorites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  favorite_type varchar(20) NOT NULL CHECK (favorite_type IN ('meal','menu','recipe')),
  reference_id text NOT NULL,
  snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(user_id, favorite_type, reference_id)
);
CREATE INDEX IF NOT EXISTS ix_favorites_user_created ON favorites(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  meal_record_id uuid REFERENCES meal_records(id) ON DELETE SET NULL,
  document_type varchar(20) NOT NULL DEFAULT 'pdf' CHECK (document_type IN ('pdf','image','other')),
  title text NOT NULL,
  storage_provider varchar(30) NOT NULL DEFAULT 'external',
  storage_key text NOT NULL,
  file_name text NOT NULL,
  mime_type text NOT NULL DEFAULT 'application/pdf',
  size_bytes bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_user_documents_user_created ON user_documents(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS shopping_lists (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  title text NOT NULL DEFAULT '장바구니',
  status varchar(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','archived')),
  source_meal_record_id uuid REFERENCES meal_records(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_shopping_lists_user_status ON shopping_lists(user_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS shopping_list_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  shopping_list_id uuid NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,
  ingredient_id bigint,
  ingredient_name text NOT NULL,
  amount numeric(10,2),
  unit varchar(30),
  is_checked boolean NOT NULL DEFAULT false,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_shopping_items_list_order ON shopping_list_items(shopping_list_id, sort_order, created_at);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  user_agent text,
  ip_address inet
);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_active ON refresh_tokens(user_id, expires_at DESC) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS user_events (
  id bigserial PRIMARY KEY,
  user_id uuid REFERENCES app_users(id) ON DELETE SET NULL,
  event_name varchar(80) NOT NULL,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_user_events_name_created ON user_events(event_name, created_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_app_users_updated_at ON app_users;
CREATE TRIGGER trg_app_users_updated_at BEFORE UPDATE ON app_users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_user_profiles_updated_at ON user_profiles;
CREATE TRIGGER trg_user_profiles_updated_at BEFORE UPDATE ON user_profiles FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_meal_records_updated_at ON meal_records;
CREATE TRIGGER trg_meal_records_updated_at BEFORE UPDATE ON meal_records FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_shopping_lists_updated_at ON shopping_lists;
CREATE TRIGGER trg_shopping_lists_updated_at BEFORE UPDATE ON shopping_lists FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
