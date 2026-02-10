"""
Tests for the run.py launcher script.

Validates each step of the launcher without actually starting services.
"""
import subprocess
import sys
import urllib.error
from unittest.mock import patch, MagicMock, Mock

import pytest

# Import functions from run.py at project root
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import run


class TestCheckPythonDeps:
    """Test Python dependency checking."""

    def test_all_deps_present(self):
        """All required packages are installed in the test environment."""
        assert run.check_python_deps() is True

    @patch("builtins.__import__", side_effect=ImportError("no module"))
    def test_missing_dep_returns_false(self, mock_import):
        assert run.check_python_deps() is False


class TestCheckDocker:
    """Test Docker availability checking."""

    @patch("shutil.which", return_value=None)
    def test_docker_not_in_path(self, mock_which):
        assert run.check_docker() is False

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_docker_daemon_not_running(self, mock_run, mock_which):
        mock_run.return_value = Mock(returncode=1)
        assert run.check_docker() is False

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_docker_running(self, mock_run, mock_which):
        mock_run.return_value = Mock(returncode=0)
        assert run.check_docker() is True

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=10))
    def test_docker_timeout(self, mock_run, mock_which):
        assert run.check_docker() is False


class TestStartQdrant:
    """Test Qdrant startup via docker-compose."""

    @patch("subprocess.run")
    def test_start_success(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        assert run.start_qdrant() is True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_fallback_to_docker_compose_v1(self, mock_run):
        """Falls back to docker-compose (v1) if docker compose (v2) fails."""
        mock_run.side_effect = [
            Mock(returncode=1, stderr="unknown command"),  # v2 fails
            Mock(returncode=0),  # v1 succeeds
        ]
        assert run.start_qdrant() is True
        assert mock_run.call_count == 2

    @patch("subprocess.run")
    def test_both_fail(self, mock_run):
        mock_run.return_value = Mock(returncode=1, stderr="error")
        assert run.start_qdrant() is False

    @patch("os.path.exists", return_value=False)
    def test_no_compose_file(self, mock_exists):
        assert run.start_qdrant() is False


class TestWaitForQdrant:
    """Test Qdrant health check waiting."""

    @patch("urllib.request.urlopen")
    def test_healthy_immediately(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__ = Mock(return_value=Mock(status=200))
        mock_resp.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert run.wait_for_qdrant() is True

    @patch("run.MAX_WAIT_SECONDS", 1)
    @patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused"))
    def test_timeout_returns_false(self, mock_urlopen):
        assert run.wait_for_qdrant() is False

    @patch("urllib.request.urlopen")
    def test_healthy_after_retries(self, mock_urlopen):
        """Becomes healthy after initial failures."""
        mock_resp = MagicMock()
        mock_resp.__enter__ = Mock(return_value=Mock(status=200))
        mock_resp.__exit__ = Mock(return_value=False)

        mock_urlopen.side_effect = [
            urllib.error.URLError("refused"),
            urllib.error.URLError("refused"),
            mock_resp,
        ]

        assert run.wait_for_qdrant() is True


class TestMainFlow:
    """Test the main() orchestration flow."""

    @patch("run.launch_app")
    @patch("run.wait_for_qdrant", return_value=True)
    @patch("run.start_qdrant", return_value=True)
    @patch("run.check_docker", return_value=True)
    @patch("run.check_python_deps", return_value=True)
    def test_full_success_flow(self, mock_deps, mock_docker, mock_start, mock_wait, mock_launch):
        result = run.main()
        assert result == 0
        mock_deps.assert_called_once()
        mock_docker.assert_called_once()
        mock_start.assert_called_once()
        mock_wait.assert_called_once()
        mock_launch.assert_called_once()

    @patch("run.check_python_deps", return_value=False)
    def test_missing_deps_exits(self, mock_deps):
        result = run.main()
        assert result == 1

    @patch("run.launch_app")
    @patch("run.check_docker", return_value=False)
    @patch("run.check_python_deps", return_value=True)
    def test_no_docker_still_launches_app(self, mock_deps, mock_docker, mock_launch):
        """App launches even without Docker (just no vector search)."""
        result = run.main()
        assert result == 0
        mock_launch.assert_called_once()

    @patch("run.launch_app")
    @patch("run.start_qdrant", return_value=False)
    @patch("run.check_docker", return_value=True)
    @patch("run.check_python_deps", return_value=True)
    def test_qdrant_start_fails_still_launches(self, mock_deps, mock_docker, mock_start, mock_launch):
        result = run.main()
        assert result == 0
        mock_launch.assert_called_once()

    @patch("run.launch_app")
    @patch("run.wait_for_qdrant", return_value=False)
    @patch("run.start_qdrant", return_value=True)
    @patch("run.check_docker", return_value=True)
    @patch("run.check_python_deps", return_value=True)
    def test_qdrant_unhealthy_still_launches(self, mock_deps, mock_docker, mock_start,
                                              mock_wait, mock_launch):
        """App launches even if Qdrant doesn't become healthy."""
        result = run.main()
        assert result == 0
        mock_launch.assert_called_once()


class TestLaunchApp:
    """Test the app launcher function."""

    @patch("threading.Thread")
    @patch("subprocess.run")
    def test_launch_calls_python_m_src(self, mock_run, mock_thread):
        mock_t = Mock()
        mock_thread.return_value = mock_t
        run.launch_app()
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == sys.executable
        assert args[1:] == ["-m", "src"]

    @patch("threading.Thread")
    @patch("subprocess.run")
    def test_launch_starts_browser_thread(self, mock_run, mock_thread):
        mock_t = Mock()
        mock_thread.return_value = mock_t
        run.launch_app()
        mock_thread.assert_called_once()
        mock_t.start.assert_called_once()
        assert mock_thread.call_args[1]["daemon"] is True
