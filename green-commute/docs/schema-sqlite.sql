-- SQLite schema for a new GreenGo database. Existing databases use scripts.upgrade_db.

PRAGMA foreign_keys=ON;

CREATE TABLE emission_factors (
	id INTEGER NOT NULL,
	rule_id INTEGER NOT NULL,
	mode VARCHAR(12) NOT NULL,
	grams_per_km INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_rule_mode_factor UNIQUE (rule_id, mode),
	FOREIGN KEY(rule_id) REFERENCES emission_rules (id)
);

CREATE TABLE emission_rules (
	id INTEGER NOT NULL,
	version VARCHAR(32) NOT NULL,
	name VARCHAR(120) NOT NULL,
	baseline_g_per_km INTEGER NOT NULL,
	points_per_kg INTEGER NOT NULL,
	active BOOLEAN NOT NULL,
	effective_from DATETIME NOT NULL,
	effective_to DATETIME,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE inventory_movements (
	id INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	kind VARCHAR(24) NOT NULL,
	operation_id VARCHAR(72) NOT NULL,
	reference_id INTEGER,
	quantity INTEGER NOT NULL,
	before_stock INTEGER NOT NULL,
	after_stock INTEGER NOT NULL,
	note VARCHAR(200) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_inventory_operation UNIQUE (operation_id),
	FOREIGN KEY(product_id) REFERENCES products (id)
);

CREATE TABLE merchant_categories (
	id INTEGER NOT NULL,
	merchant_id INTEGER NOT NULL,
	name VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_merchant_category_name UNIQUE (merchant_id, name),
	FOREIGN KEY(merchant_id) REFERENCES users (id)
);

CREATE TABLE outbox_events (
	id INTEGER NOT NULL,
	kind VARCHAR(40) NOT NULL,
	ref_id INTEGER NOT NULL,
	state VARCHAR(16) NOT NULL,
	attempts INTEGER NOT NULL,
	error TEXT,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_outbox_business UNIQUE (kind, ref_id)
);

CREATE TABLE point_transactions (
	id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	kind VARCHAR(20) NOT NULL,
	reference_id INTEGER NOT NULL,
	delta INTEGER NOT NULL,
	balance_after INTEGER NOT NULL,
	description VARCHAR(200) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_ledger_business UNIQUE (kind, reference_id),
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE products (
	id INTEGER NOT NULL,
	merchant_id INTEGER NOT NULL,
	name VARCHAR(90) NOT NULL,
	description VARCHAR(300) NOT NULL,
	category VARCHAR(40) NOT NULL,
	icon VARCHAR(16) NOT NULL,
	cost INTEGER NOT NULL,
	stock INTEGER NOT NULL,
	active BOOLEAN NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(merchant_id) REFERENCES users (id)
);

CREATE TABLE redemptions (
	id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	product_name VARCHAR(90) NOT NULL,
	points INTEGER NOT NULL,
	status VARCHAR(25) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME,
	fulfilled_at DATETIME,
	refunded_at DATETIME,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(product_id) REFERENCES products (id)
);

CREATE TABLE settlements (
	redemption_id INTEGER NOT NULL,
	merchant_id INTEGER NOT NULL,
	points INTEGER NOT NULL,
	status VARCHAR(20) NOT NULL,
	created_at DATETIME NOT NULL,
	settled_at DATETIME,
	cancelled_at DATETIME,
	PRIMARY KEY (redemption_id),
	FOREIGN KEY(redemption_id) REFERENCES redemptions (id),
	FOREIGN KEY(merchant_id) REFERENCES users (id)
);

CREATE TABLE support_messages (
	id INTEGER NOT NULL,
	ticket_id INTEGER NOT NULL,
	sender_id INTEGER NOT NULL,
	content TEXT NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(ticket_id) REFERENCES support_tickets (id),
	FOREIGN KEY(sender_id) REFERENCES users (id)
);

CREATE TABLE support_tickets (
	id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	category VARCHAR(24) NOT NULL,
	subject VARCHAR(100) NOT NULL,
	status VARCHAR(20) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE trip_calculations (
	trip_id INTEGER NOT NULL,
	rule_id INTEGER NOT NULL,
	rule_version VARCHAR(32) NOT NULL,
	baseline_g_per_km INTEGER NOT NULL,
	mode_g_per_km INTEGER NOT NULL,
	points_per_kg INTEGER NOT NULL,
	distance_m INTEGER NOT NULL,
	saved_g INTEGER NOT NULL,
	points INTEGER NOT NULL,
	calculated_at DATETIME NOT NULL,
	PRIMARY KEY (trip_id),
	FOREIGN KEY(trip_id) REFERENCES trips (id),
	FOREIGN KEY(rule_id) REFERENCES emission_rules (id)
);

CREATE TABLE trip_evidence (
	id INTEGER NOT NULL,
	trip_id INTEGER NOT NULL,
	source_type VARCHAR(20) NOT NULL,
	external_reference VARCHAR(120),
	payload TEXT,
	captured_at DATETIME NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(trip_id) REFERENCES trips (id)
);

CREATE TABLE trips (
	id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	client_trip_id VARCHAR(72) NOT NULL,
	mode VARCHAR(12) NOT NULL,
	distance_m INTEGER NOT NULL,
	saved_g INTEGER NOT NULL,
	points INTEGER NOT NULL,
	status VARCHAR(18) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_user_trip UNIQUE (user_id, client_trip_id),
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE users (
	id INTEGER NOT NULL,
	username VARCHAR(48) NOT NULL,
	password_hash VARCHAR(200) NOT NULL,
	display_name VARCHAR(80) NOT NULL,
	role VARCHAR(15) NOT NULL,
	balance INTEGER NOT NULL,
	enabled BOOLEAN DEFAULT 1 NOT NULL,
	session_version INTEGER DEFAULT 0 NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);

CREATE INDEX ix_emission_factors_rule_id ON emission_factors (rule_id);

CREATE INDEX ix_emission_rules_active ON emission_rules (active);

CREATE UNIQUE INDEX ix_emission_rules_version ON emission_rules (version);

CREATE INDEX ix_inventory_movements_product_id ON inventory_movements (product_id);

CREATE INDEX ix_point_transactions_user_id ON point_transactions (user_id);

CREATE INDEX ix_support_messages_ticket_id ON support_messages (ticket_id);

CREATE INDEX ix_support_tickets_status ON support_tickets (status);

CREATE INDEX ix_support_tickets_user_id ON support_tickets (user_id);

CREATE INDEX ix_trip_calculations_rule_id ON trip_calculations (rule_id);

CREATE INDEX ix_trip_evidence_trip_id ON trip_evidence (trip_id);

CREATE INDEX ix_trips_user_id ON trips (user_id);

CREATE UNIQUE INDEX ix_users_username ON users (username);
