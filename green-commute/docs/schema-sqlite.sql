-- Actual SQLite schema introspected from the running demo database.

CREATE INDEX ix_point_transactions_user_id ON point_transactions (user_id);

CREATE INDEX ix_trips_user_id ON trips (user_id);

CREATE UNIQUE INDEX ix_users_username ON users (username);

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
	PRIMARY KEY (redemption_id), 
	FOREIGN KEY(redemption_id) REFERENCES redemptions (id), 
	FOREIGN KEY(merchant_id) REFERENCES users (id)
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
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
