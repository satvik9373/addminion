from datetime import datetime, timezone
from pathlib import Path

from core.domain import Lead, User, Workspace
from persistence.mappers import lead_from_row, user_from_row, workspace_from_row
from persistence.postgres import (
    PostgresLeadRepository,
    PostgresUserRepository,
    PostgresWorkspaceRepository,
)


class FakeCursor:
    def __init__(self, rows=(), description=()):
        self.rows = list(rows)
        self.description = description
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.executed = (sql, params)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows=(), description=()):
        self.cursor_instance = FakeCursor(rows, description)
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_persistence_mappers_keep_rows_out_of_domain():
    now = datetime.now(timezone.utc)
    user = user_from_row({
        'id': 'u1', 'email': 'u@example.com',
        'display_name': 'User', 'created_at': now,
    })
    workspace = workspace_from_row({
        'id': 'w1', 'owner_user_id': 'u1', 'name': 'Workspace',
        'created_at': now,
    })
    lead = lead_from_row({
        'id': 'l1', 'workspace_id': 'w1', 'name': 'Lead',
        'company_name': 'Company', 'website_url': None, 'source': 'test',
        'discovered_at': now, 'metadata': '{"sector": "tech"}',
    })

    assert isinstance(user, User)
    assert isinstance(workspace, Workspace)
    assert isinstance(lead, Lead)
    assert lead.metadata == {'sector': 'tech'}


def test_postgres_user_repository_uses_parameterized_sql():
    now = datetime.now(timezone.utc)
    connection = FakeConnection()
    repository = PostgresUserRepository(lambda: connection)

    repository.save(User(id='u1', email='u@example.com', created_at=now))

    sql, params = connection.cursor_instance.executed
    assert 'INSERT INTO users' in sql
    assert '%s' in sql
    assert params[1] == 'u@example.com'
    assert connection.committed
    assert connection.closed


def test_postgres_workspace_repository_maps_owned_workspace():
    now = datetime.now(timezone.utc)
    connection = FakeConnection(
        rows=[('w1', 'u1', 'Workspace', now)],
        description=[('id',), ('owner_user_id',), ('name',), ('created_at',)],
    )
    workspace = PostgresWorkspaceRepository(lambda: connection).get('w1')

    assert workspace is not None
    assert workspace.owner_user_id == 'u1'


def test_postgres_lead_repository_requires_workspace():
    repository = PostgresLeadRepository(lambda: FakeConnection())

    try:
        repository.save(Lead(name='Without workspace'))
    except ValueError as exc:
        assert 'workspace_id' in str(exc)
    else:
        raise AssertionError('missing workspace_id must be rejected')


def test_migration_defines_tenant_foreign_keys_and_indexes():
    migration = Path(__file__).parents[1] / 'migrations' / '001_initial_persistence.sql'
    sql = migration.read_text(encoding='utf-8')

    assert 'CREATE TABLE workspaces' in sql
    assert 'owner_user_id UUID NOT NULL REFERENCES users(id)' in sql
    assert 'workspace_id UUID NOT NULL REFERENCES workspaces(id)' in sql
    assert 'idx_leads_workspace_id' in sql
    assert 'email TEXT NOT NULL UNIQUE' in sql
