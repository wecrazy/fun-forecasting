"""Initial schema: assets, forecast_jobs, forecast_predictions.

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("asset_type", sa.String(16), nullable=False),
        sa.Column("currency_native", sa.String(8), nullable=False, server_default="usd"),
    )

    op.create_table(
        "forecast_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="usd"),
        sa.Column("horizon_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("history_days", sa.String(16), nullable=False, server_default="max"),
        sa.Column("optuna_trials", sa.Integer, nullable=False, server_default="60"),
        sa.Column("include_exog", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("celery_task_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "forecast_predictions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("forecast_jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("predicted_price", sa.Float, nullable=False),
        sa.Column("predicted_price_usd", sa.Float, nullable=True),
        sa.Column("predicted_price_idr", sa.Float, nullable=True),
        sa.Column("predicted_return", sa.Float, nullable=True),
        sa.Column("upper_bound", sa.Float, nullable=True),
        sa.Column("lower_bound", sa.Float, nullable=True),
        sa.Column("xgb_price", sa.Float, nullable=True),
        sa.Column("sarimax_price", sa.Float, nullable=True),
        sa.Column("prophet_price", sa.Float, nullable=True),
        sa.Column("lstm_price", sa.Float, nullable=True),
    )

    # Seed static assets
    op.bulk_insert(
        sa.table(
            "assets",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("asset_type", sa.String),
            sa.column("currency_native", sa.String),
        ),
        [
            {"id": "funtoken", "name": "FUNToken", "asset_type": "crypto", "currency_native": "usd"},
            {"id": "bitcoin", "name": "Bitcoin", "asset_type": "crypto", "currency_native": "usd"},
            {"id": "ethereum", "name": "Ethereum", "asset_type": "crypto", "currency_native": "usd"},
            {"id": "binancecoin", "name": "BNB", "asset_type": "crypto", "currency_native": "usd"},
            {"id": "solana", "name": "Solana", "asset_type": "crypto", "currency_native": "usd"},
            {"id": "GOTO.JK", "name": "Gojek Tokopedia", "asset_type": "stock", "currency_native": "idr"},
            {"id": "BBCA.JK", "name": "Bank Central Asia", "asset_type": "stock", "currency_native": "idr"},
            {"id": "TLKM.JK", "name": "Telkom Indonesia", "asset_type": "stock", "currency_native": "idr"},
            {"id": "BBRI.JK", "name": "Bank Rakyat Indonesia", "asset_type": "stock", "currency_native": "idr"},
            {"id": "ASII.JK", "name": "Astra International", "asset_type": "stock", "currency_native": "idr"},
        ],
    )


def downgrade() -> None:
    op.drop_table("forecast_predictions")
    op.drop_table("forecast_jobs")
    op.drop_table("assets")
