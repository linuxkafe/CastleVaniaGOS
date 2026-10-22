"""Tests for temporal.py — decay model and staleness detection."""

import math
import os
import subprocess
import sys
import textwrap
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import pytest
import lib.memory.temporal as temporal
from lib.memory.temporal import (
    TemporalDoc,
    TemporalIndex,
    _parse_dt,
    FRESH_DAYS,
    DECAY_LAMBDA,
)


class TestTemporalDoc:
    def _make_doc(self, **kwargs):
        defaults = dict(
            doc_id="SD-TEST",
            created=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
            epistemic_state="SUPORTADA",
        )
        defaults.update(kwargs)
        return TemporalDoc(**defaults)

    def test_fresh_doc_full_relevance(self):
        doc = self._make_doc()
        assert doc.temporal_decay() == 1.0

    def test_8day_doc_decay(self):
        doc = self._make_doc(
            created=datetime.now(timezone.utc) - timedelta(days=8),
            last_accessed=datetime.now(timezone.utc) - timedelta(days=8),
        )
        decay = doc.temporal_decay()
        assert 0.9 < decay < 1.0

    def test_30day_doc_decay(self):
        doc = self._make_doc(
            created=datetime.now(timezone.utc) - timedelta(days=30),
            last_accessed=datetime.now(timezone.utc) - timedelta(days=30),
        )
        decay = doc.temporal_decay()
        assert decay < 0.5

    def test_60day_doc_stale(self):
        doc = self._make_doc(
            created=datetime.now(timezone.utc) - timedelta(days=60),
            last_accessed=datetime.now(timezone.utc) - timedelta(days=60),
        )
        decay = doc.temporal_decay()
        assert decay < 0.1

    def test_decay_at_specific_time(self):
        doc = self._make_doc(
            created=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_accessed=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        at = datetime(2026, 1, 11, tzinfo=timezone.utc)
        decay = doc.temporal_decay(at=at)
        expected = math.exp(-DECAY_LAMBDA * (10 - FRESH_DAYS))
        assert abs(decay - expected) < 0.001

    def test_archived_doc(self):
        doc = self._make_doc(
            archived_at=datetime.now(timezone.utc),
        )
        assert doc.is_archived

    def test_not_archived(self):
        doc = self._make_doc()
        assert not doc.is_archived

    def test_age_days(self):
        doc = self._make_doc(
            created=datetime.now(timezone.utc) - timedelta(days=5),
        )
        assert 4.9 < doc.age_days < 5.1

    def test_staleness_days(self):
        doc = self._make_doc(
            last_accessed=datetime.now(timezone.utc) - timedelta(days=10),
        )
        assert 9.9 < doc.staleness_days < 10.1


class TestParseDt:
    """Cada teste possui um fixture com o defeito que julga (T358)."""

    def test_accepts_pure_date(self):
        # YAML converte `created: 2026-07-09` sem aspas num datetime.date.
        # datetime e subclasse de date, por isso uma data pura caia fora dos
        # ramos datetime e str e _parse_dt devolvia None.
        got = _parse_dt(date(2026, 7, 9))
        assert got == datetime(2026, 7, 9, tzinfo=timezone.utc)

    def test_naive_datetime_still_gets_utc(self):
        got = _parse_dt(datetime(2026, 7, 9, 12, 0, 0))
        assert got == datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

    def test_aware_datetime_kept(self):
        aware = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
        assert _parse_dt(aware) == aware

    def test_iso_string_still_parses(self):
        assert _parse_dt("2026-07-09") == datetime(2026, 7, 9, tzinfo=timezone.utc)

    def test_garbage_returns_none(self):
        assert _parse_dt("nao-e-uma-data") is None
        assert _parse_dt(None) is None


class TestTemporalIndexLoader:
    """T358 — o _load() nunca foi testado, que e porque os defeitos sobreviveram."""

    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        shadow = tmp_path / "aes" / "shadow"
        (shadow / "archive").mkdir(parents=True)
        monkeypatch.setattr(temporal, "SHADOW_DIR", shadow)
        monkeypatch.setattr(temporal, "ARCHIVE_DIR", shadow / "archive")
        return shadow

    def _write(self, shadow, name, body):
        (shadow / name).write_text(textwrap.dedent(body), encoding="utf-8")

    def test_date_typed_created_is_indexed(self, project):
        self._write(project, "SD-FIX-date.md", """\
            ---
            id: SD-FIX-date
            created: 2026-07-09
            epistemic_state: SUPORTADA
            ---
            body
            """)
        docs = TemporalIndex().docs()
        assert "SD-FIX-date" in docs
        assert docs["SD-FIX-date"].created == datetime(2026, 7, 9, tzinfo=timezone.utc)

    def test_scalar_provenance_does_not_crash_the_index(self, project):
        # provenance como escalar nao tem .get: rebentava o indice INTEIRO com
        # AttributeError, o que tornava o painel de memoria inutilizavel se
        # um unico doc tivesse esse formato.
        self._write(project, "SD-FIX-prov.md", """\
            ---
            id: SD-FIX-prov
            created: "2026-07-09"
            provenance: nao-e-um-mapping
            ---
            body
            """)
        docs = TemporalIndex().docs()
        assert "SD-FIX-prov" in docs
        assert docs["SD-FIX-prov"].source_ticket is None

    def test_mapping_provenance_still_read(self, project):
        self._write(project, "SD-FIX-map.md", """\
            ---
            id: SD-FIX-map
            created: "2026-07-09"
            provenance:
              source_ticket: T358
            ---
            body
            """)
        assert TemporalIndex().docs()["SD-FIX-map"].source_ticket == "T358"

    def test_absent_provenance_is_not_a_crash(self, project):
        self._write(project, "SD-FIX-noprov.md", """\
            ---
            id: SD-FIX-noprov
            created: "2026-07-09"
            ---
            body
            """)
        assert TemporalIndex().docs()["SD-FIX-noprov"].source_ticket is None

    def test_missing_created_is_dropped(self, project):
        # Residual conhecido, deliberadamente fixado: sem `created` nao ha
        # data de criacao, logo nao ha indice. Este `continue` silencioso e o
        # que escondeu o bug da data durante meses — por isso fica testado
        # explicitamente, para deixar de ser invisivel.
        self._write(project, "SD-FIX-nocreated.md", """\
            ---
            id: SD-FIX-nocreated
            ---
            body
            """)
        assert "SD-FIX-nocreated" not in TemporalIndex().docs()

    def test_aes_root_honours_environment(self, tmp_path):
        # Testado por subporque: AES_ROOT e lido no import, e recarregar o
        # modulo sujaria os outros testes da mesma sessao.
        shadow = tmp_path / "aes" / "shadow"
        (shadow / "archive").mkdir(parents=True)
        (shadow / "SD-FIX-env.md").write_text(
            '---\nid: SD-FIX-env\ncreated: "2026-07-09"\n---\n', encoding="utf-8"
        )
        repo = str(Path(__file__).resolve().parents[2])
        env = dict(os.environ, AES_ROOT=str(tmp_path), PYTHONPATH=repo)
        out = subprocess.run(
            [
                sys.executable,
                "-c",
                "from lib.memory.temporal import AES_ROOT, TemporalIndex;"
                "print(AES_ROOT);print(len(TemporalIndex().docs()))",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
            check=True,
        )
        root, count = out.stdout.split()
        assert root == str(tmp_path)
        assert int(count) == 1
