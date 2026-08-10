"""Regression test for the db_session fixture's transaction isolation.

A prior version of the ``db_session`` fixture only called
``session.rollback()`` on teardown — which ``AsyncSession.__aexit__`` already
does — with nothing binding the session to an outer, always-rolled-back
transaction. As a result, any test that itself called ``session.commit()``
left its rows permanently in the database, visible to every test that ran
after it.

This pair of tests is deliberately order-dependent: it is testing the
isolation guarantee itself, so it must exercise a real commit in one test and
observe its absence in a later one. Pytest collects tests within a module in
file order, so ``test_aa_...`` runs before ``test_bb_...``. Do not reorder,
rename out of aa/bb order, or split these into separate files.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Run


@pytest.mark.asyncio
async def test_aa_commit_a_run(db_session: AsyncSession):
    """Commit a row the way a real test might, to probe for leakage."""
    db_session.add(Run())
    await db_session.commit()


@pytest.mark.asyncio
async def test_bb_runs_table_is_empty(db_session: AsyncSession):
    """If isolation works, the previous test's commit must not be visible here."""
    count = await db_session.scalar(select(func.count()).select_from(Run))
    assert count == 0
