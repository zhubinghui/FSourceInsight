"""Database-owned spend admission. Prices/ceilings are trusted operator inputs.

A ceiling is a reviewed supplier billing contract, NOT a tokenizer estimate or
proof against a supplier that violates its contract. Missing terms fail closed.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import time
import uuid
import hashlib

from flask import current_app
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.llm import LLMBudgetGate, LLMReservation, LLMUsageLog, LLMReconciliation


class BudgetError(RuntimeError):
    """No further billable attempt is authorized by the accounting state."""


UNIT = Decimal('0.000001')


def money(value):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or value < 0 or value > Decimal('999999999999'):
            raise ValueError
        return value.quantize(UNIT, rounding=ROUND_CEILING)
    except (InvalidOperation, ValueError, TypeError):
        raise BudgetError('Invalid budget or billing price') from None


@dataclass(frozen=True)
class Quote:
    input_limit: int
    output_limit: int
    input_price: Decimal
    output_price: Decimal
    reserved: Decimal


def quote(config):
    limits = (config.billing_input_limit, config.billing_output_limit)
    if any(type(limit) is not int or not 1 <= limit <= 10_000_000 for limit in limits):
        raise BudgetError('Reviewed billing token ceilings required')
    max_tokens = config.max_tokens if config.max_tokens is not None else 4096
    if type(max_tokens) is not int or not 1 <= max_tokens <= limits[1]:
        raise BudgetError('Requested output exceeds billing token ceiling')
    input_price, output_price = money(config.cost_per_1k_input), money(config.cost_per_1k_output)
    reserved = money((input_price * limits[0] + output_price * limits[1]) / 1000)
    return Quote(*limits, input_price, output_price, reserved)


def now():
    return datetime.fromtimestamp(time.time(), timezone.utc).replace(tzinfo=None)


@contextmanager
def transaction():
    # INSERT (including conflict update/no-op) obtains the write lock BEFORE
    # reading totals: SQLite also serializes across independent connections.
    with Session(db.engine) as session, session.begin():
        if db.engine.dialect.name == 'mysql':
            from sqlalchemy.dialects.mysql import insert
            statement = insert(LLMBudgetGate).values(id=1).on_duplicate_key_update(id=1)
        elif db.engine.dialect.name == 'sqlite':
            from sqlalchemy.dialects.sqlite import insert
            statement = insert(LLMBudgetGate).values(id=1).on_conflict_do_nothing()
        else:
            raise BudgetError('Unsupported budget database')
        session.execute(statement)
        session.execute(select(LLMBudgetGate).where(LLMBudgetGate.id == 1).with_for_update()).scalar_one()
        yield session


def reserve(config, task, learning_attempt=None, messages=None, discovery_job=None, refresh_job=None):
    quoted = quote(config)
    limit = money(current_app.config.get('LLM_DAILY_BUDGET_USD', 0))
    endpoint_hash = hashlib.sha256((config.api_base_url or '').encode()).hexdigest()
    with transaction() as session:
        timestamp = now()
        day = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        # A linked usage log is already included via its reservation. Legacy
        # logs stay intact; an unpriced legacy call today blocks paid admission.
        legacy = select(LLMUsageLog).where(
            LLMUsageLog.created_at >= day, LLMUsageLog.created_at < day + timedelta(days=1),
            ~select(LLMReservation.id).where(LLMReservation.usage_id == LLMUsageLog.id).exists())
        legacy = legacy.subquery()
        if session.scalar(select(func.count()).select_from(legacy).where(legacy.c.cost_usd.is_(None))):
            raise BudgetError('Unpriced legacy usage requires reconciliation')
        if session.scalar(select(func.count()).select_from(LLMReservation).where(LLMReservation.state == 'overrun')):
            raise BudgetError('Billing ceiling overrun requires reconciliation')
        disproved = select(LLMReservation.id).join(LLMUsageLog, LLMUsageLog.id == LLMReservation.usage_id).where(
            LLMReservation.provider == config.provider, LLMReservation.model == config.model,
            LLMReservation.endpoint_hash == endpoint_hash,
            LLMUsageLog.error_message == 'BillingCeilingOverrun',
            or_(LLMUsageLog.input_tokens > quoted.input_limit, LLMUsageLog.output_tokens > quoted.output_limit))
        if session.scalar(disproved.limit(1)):
            raise BudgetError('Billing ceilings below observed usage; review provider configuration')
        historic = session.scalar(select(func.coalesce(func.sum(legacy.c.cost_usd), 0)))
        # Unknown/in-flight reservations carry forward across midnight. They
        # are never released by TTL, a worker retry, or a process restart.
        charges = session.scalar(select(func.coalesce(func.sum(case(
            (LLMReservation.state.in_(('settled', 'reconciled')), LLMReservation.actual_usd),
            else_=LLMReservation.reserved_usd)), 0)).where(or_(
                LLMReservation.billing_day == day.date(), ~LLMReservation.state.in_(('settled', 'reconciled')))))
        if limit and money(historic) + money(charges) + quoted.reserved > limit:
            raise BudgetError('Daily LLM budget exceeded')
        if task == 'crawl_schema' or learning_attempt is not None:
            if task != 'crawl_schema' or not learning_attempt:
                raise BudgetError('Persisted learning attempt required')
            from app.crawlers.learning import admit
            admit(session, learning_attempt, messages, quoted, day, config)
        if discovery_job is not None:
            if task != 'company_analysis' or learning_attempt is not None or not discovery_job:
                raise BudgetError('Persisted discovery job required')
            from app.llm.startup_analysis import admit as admit_discovery
            admit_discovery(session, discovery_job, messages, config)
        if refresh_job is not None:
            if (task != 'company_analysis' or learning_attempt is not None or discovery_job is not None
                    or not refresh_job):
                raise BudgetError('Persisted company refresh job required')
            from app.llm.company_refresh import admit as admit_refresh
            admit_refresh(session, refresh_job, messages, config)
        reservation = LLMReservation(
            id=str(uuid.uuid4()), config_id=config.id, task_type=task, billing_day=day.date(),
            learning_attempt_id=learning_attempt, startup_analysis_id=discovery_job,
            company_refresh_id=refresh_job,
            provider=config.provider, model=config.model,
            endpoint_hash=endpoint_hash,
            input_limit=quoted.input_limit, output_limit=quoted.output_limit,
            input_price=quoted.input_price, output_price=quoted.output_price,
            reserved_usd=quoted.reserved, state='reserved', created_at=timestamp)
        session.add(reservation)
        permit = reservation.id
    return permit


def settle(permit, log, usage):
    """Atomically settle and link the independent usage log. Failure keeps hold."""
    failure = None
    with transaction() as session:
        reservation = session.get(LLMReservation, permit)
        if reservation is None or reservation.state != 'reserved':
            raise BudgetError('Reservation is not pending')
        values = (getattr(usage, 'prompt_tokens', None), getattr(usage, 'completion_tokens', None))
        total = getattr(usage, 'total_tokens', None)
        if (any(type(n) is not int or not 0 <= n <= 100_000_000 for n in values)
                or total is not None and (type(total) is not int or total != sum(values))):
            reservation.state = 'unknown'
            log.input_tokens = log.output_tokens = log.cost_usd = None
            log.success = False
            log.error_message = log.error_message or 'UnknownUsage'
            failure = BudgetError('LLM usage unknown; reservation retained')
        else:
            log.input_tokens, log.output_tokens = values
            actual = money((reservation.input_price * values[0] + reservation.output_price * values[1]) / 1000)
            reservation.actual_usd = actual
            # Preserve even a supplier violation beyond the legacy log's
            # NUMERIC(10,6). Never truncate or roll back the larger audit charge.
            log.cost_usd = actual if actual <= Decimal('9999.999999') else None
            reservation.state = 'settled'
            if values[0] > reservation.input_limit or values[1] > reservation.output_limit:
                reservation.state = 'overrun'
                log.success, log.error_message = False, 'BillingCeilingOverrun'
                failure = BudgetError('Billing ceiling overrun requires reconciliation')
        session.add(log)
        session.flush()
        reservation.usage_id, reservation.settled_at = log.id, now()
    return failure


def reconcile(permit, expected_state, final_cost, evidence_note, actor_id):
    """Operator attests stopped execution and a FINAL supplier bill, not an estimate."""
    amount = money(final_cost)
    if not isinstance(evidence_note, str) or not 1 <= len(evidence_note.strip()) <= 500:
        raise ValueError('Final supplier evidence reference required')
    with transaction() as session:
        reservation = session.get(LLMReservation, permit)
        if (reservation is None or reservation.state not in {'reserved', 'unknown', 'overrun'}
                or reservation.state != expected_state or reservation.reconciliation is not None):
            raise BudgetError('Reservation changed or already reconciled')
        session.add(LLMReconciliation(reservation_id=permit, final_cost=amount,
            evidence_note=evidence_note.strip(), actor_id=actor_id, created_at=now()))
        reservation.actual_usd, reservation.state, reservation.settled_at = amount, 'reconciled', now()
