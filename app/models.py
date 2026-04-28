from flask_login import UserMixin
from app import db
from datetime import datetime, timezone


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)  # primary keys are required by SQLAlchemy
    email = db.Column(db.String(100))
    password = db.Column(db.String(256))  # Scrypt passwords are ~150 chars
    name = db.Column(db.String(1000))
    admin = db.Column(db.Boolean)
    is_global_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)
    account_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    is_account_owner = db.Column(db.Boolean, default=True, nullable=False, server_default=db.true())
    owner_user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', name='fk_user_owner_user_id'), nullable=True
    )
    twofa_enabled = db.Column(db.Boolean, default=False, server_default=db.false(), nullable=False)
    twofa_secret = db.Column(db.String(500), nullable=True)   # Fernet-encrypted TOTP secret
    twofa_backup_codes = db.Column(db.Text, nullable=True)    # JSON array of scrypt-hashed backup codes
    # Marks an account owner as an Apple/store reviewer test account. Reviewer
    # accounts bypass payment-subscription enforcement and remain active.
    is_review_user = db.Column(
        db.Boolean, default=False, server_default=db.false(), nullable=False
    )

    # Relationships
    guests = db.relationship(
        'User',
        foreign_keys='User.account_owner_id',
        backref=db.backref('account_owner', remote_side=[id]),
    )
    subscriptions = db.relationship(
        'Subscription',
        back_populates='user',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )

    @property
    def active_subscription(self):
        """Return the most recent currently-active subscription, if any."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return (
            self.subscriptions.filter(
                Subscription.status.in_(["active", "trial", "grace_period"]),
                db.or_(Subscription.expires_at.is_(None), Subscription.expires_at >= now),
            )
            .order_by(Subscription.updated_at.desc(), Subscription.id.desc())
            .first()
        )

    # Constraints
    __table_args__ = (
        db.UniqueConstraint('email', name='uq_user_email'),
    )


class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2))
    frequency = db.Column(db.String(100))
    startdate = db.Column(db.Date)
    type = db.Column(db.String(100))
    firstdate = db.Column(db.Date)

    # Relationships
    user = db.relationship('User', backref='schedules')

    # Unique constraint per user
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='_user_schedule_uc'),)


class Scenario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2))
    frequency = db.Column(db.String(100))
    startdate = db.Column(db.Date)
    type = db.Column(db.String(100))
    firstdate = db.Column(db.Date)

    # Relationships
    user = db.relationship('User', backref='scenarios')

    # Unique constraint per user
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='_user_scenario_uc'),)


class Balance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2))
    date = db.Column(db.Date)

    # Relationships
    user = db.relationship('User', backref='balances')

    __table_args__ = (
        db.Index('ix_balance_user_id_date_id', 'user_id', 'date', 'id'),
    )


class Hold(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2))
    name = db.Column(db.String(100))
    type = db.Column(db.String(100))

    # Relationships
    user = db.relationship('User', backref='holds')


class Skip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    name = db.Column(db.String(100))
    date = db.Column(db.Date)
    amount = db.Column(db.Numeric(10, 2))
    type = db.Column(db.String(100))

    # Relationships
    user = db.relationship('User', backref='skips')


class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    value = db.Column(db.Boolean)

    # Constraints
    __table_args__ = (
        db.UniqueConstraint('name', name='uq_settings_name'),
    )


class TextSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    value = db.Column(db.String(500))

    # Constraints
    __table_args__ = (
        db.UniqueConstraint('name', name='uq_text_settings_name'),
    )


class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    email = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(500))
    server = db.Column(db.String(100))
    subjectstr = db.Column(db.String(100))
    startstr = db.Column(db.String(100))
    endstr = db.Column(db.String(100))
    # Expected sender address or domain for inbound balance emails.
    # Exact match: 'alerts@bank.com'  Domain match: '@bank.com'
    # NULL means no restriction is configured (ingestion proceeds with a warning).
    allowed_sender = db.Column(db.String(200), nullable=True)

    # Relationships
    user = db.relationship('User', backref='email_configs')


class GlobalEmailSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(500), nullable=False)
    smtp_server = db.Column(db.String(100), nullable=False)

    # Constraints - only one global email settings record allowed
    __table_args__ = (
        db.CheckConstraint('id = 1', name='single_row_check'),
    )


class AISettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    api_key = db.Column(db.String(500), nullable=True)  # Fernet-encrypted OpenAI API key
    model_version = db.Column(db.String(100), nullable=True)  # OpenAI model to use (e.g. gpt-4o-mini)
    last_updated = db.Column(db.DateTime, nullable=True)
    last_insights = db.Column(db.Text, nullable=True)  # JSON string of cached insights

    # Relationships
    user = db.relationship('User', backref='ai_settings')

    # One settings record per user
    __table_args__ = (
        db.UniqueConstraint('user_id', name='_ai_settings_user_uc'),
    )


class PasskeyCredential(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    credential_id = db.Column(db.String(512), nullable=False, unique=True, index=True)
    public_key = db.Column(db.Text, nullable=False)
    sign_count = db.Column(db.Integer, nullable=False, default=0)
    transports = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime, nullable=True)
    label = db.Column(db.String(120), nullable=True)

    # Relationships
    user = db.relationship('User', backref='passkey_credentials')


class UserToken(db.Model):
    """Opaque bearer tokens for stateless API authentication.

    The raw token is returned to the client exactly once (at creation).
    Only its SHA-256 hash is stored server-side, so a database breach cannot
    be used to impersonate users directly.
    """
    __tablename__ = 'user_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    # SHA-256 hex digest of the raw token
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)

    # Relationships
    user = db.relationship('User', backref='api_tokens')


class PasswordSetupToken(db.Model):
    """One-time password setup tokens used for payment-created users."""

    __tablename__ = 'password_setup_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship('User', backref='password_setup_tokens')


class Subscription(db.Model):
    """Normalized provider subscription state tied to account owner users."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    source = db.Column(db.String(20), nullable=False)
    environment = db.Column(db.String(20), nullable=True)
    product_id = db.Column(db.String(255), nullable=True)
    original_transaction_id = db.Column(db.String(255), nullable=True)
    latest_transaction_id = db.Column(db.String(255), nullable=True)
    external_subscription_id = db.Column(db.String(255), nullable=True)
    status = db.Column(
        db.String(20),
        nullable=False,
        default='inactive',
        server_default='inactive',
    )
    expires_at = db.Column(db.DateTime, nullable=True)
    raw_last_verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    user = db.relationship('User', back_populates='subscriptions')

    __table_args__ = (
        db.UniqueConstraint(
            'source',
            'environment',
            'original_transaction_id',
            name='uq_subscription_apple_original',
        ),
        db.UniqueConstraint(
            'source',
            'external_subscription_id',
            name='uq_subscription_external_source_id',
        ),
    )
