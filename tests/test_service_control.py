import signal
import unittest
from pathlib import Path
from unittest import mock

from weboter.app.server import list_service_processes, restart_background_service, stop_background_service
from weboter.app.state import ServiceState


class ServiceControlTests(unittest.TestCase):
    def setUp(self):
        self.state = ServiceState(
            host="127.0.0.1",
            port=34567,
            pid=43210,
            workspace_root="/tmp/weboter",
            log_path="/tmp/weboter/.weboter/service.log",
            started_at="2026-04-19T10:00:00",
        )

    def test_stop_terminates_process_group_then_force_kills(self):
        workflow_service = mock.Mock()
        workflow_service.read_service_state.return_value = self.state

        with mock.patch("weboter.app.server._process_exists", return_value=True), \
             mock.patch("weboter.app.server._is_expected_service_process", return_value=True), \
             mock.patch("weboter.app.server._wait_for_service_process_exit", side_effect=[False, True]), \
             mock.patch("weboter.app.server._signal_service_process_tree") as signal_tree:
            result = stop_background_service(workflow_service)

        self.assertEqual(result["status"], "killed")
        self.assertEqual(
            signal_tree.call_args_list,
            [mock.call(self.state.pid, signal.SIGTERM), mock.call(self.state.pid, signal.SIGKILL)],
        )
        workflow_service.remove_service_state.assert_called_once()

    def test_restart_stops_existing_service_before_starting(self):
        workflow_service = mock.Mock()
        workflow_service.read_service_state.return_value = self.state

        with mock.patch("weboter.app.server.stop_background_service", return_value={"status": "stopped", "pid": self.state.pid}) as stop_service, \
             mock.patch("weboter.app.server.start_background_service", return_value={"status": "started", "pid": 54321, "host": self.state.host, "port": self.state.port}) as start_service:
            result = restart_background_service(self.state.host, self.state.port, workflow_service)

        stop_service.assert_called_once_with(workflow_service)
        start_service.assert_called_once_with(self.state.host, self.state.port, workflow_service)
        self.assertEqual(result["status"], "restarted")
        self.assertEqual(result["previous"]["status"], "stopped")

    def test_restart_starts_directly_when_service_not_running(self):
        workflow_service = mock.Mock()
        workflow_service.read_service_state.return_value = None

        with mock.patch("weboter.app.server.start_background_service", return_value={"status": "started", "pid": 54321, "host": self.state.host, "port": self.state.port}) as start_service:
            result = restart_background_service(self.state.host, self.state.port, workflow_service)

        start_service.assert_called_once_with(self.state.host, self.state.port, workflow_service)
        self.assertEqual(result["status"], "started")
        self.assertNotIn("previous", result)

    def test_service_processes_lists_current_process_group(self):
        workflow_service = mock.Mock()
        workflow_service.read_service_state.return_value = self.state
        proc_entries = [Path("/proc/43210"), Path("/proc/50001"), Path("/proc/60000")]
        stats = {
            43210: {"pid": 43210, "ppid": 1, "pgid": 43210, "state": "S", "comm": "python"},
            50001: {"pid": 50001, "ppid": 43210, "pgid": 43210, "state": "S", "comm": "chrome"},
            60000: {"pid": 60000, "ppid": 999, "pgid": 60000, "state": "S", "comm": "other"},
        }
        cmdlines = {
            43210: ["python", "-m", "weboter", "service", "start", "--foreground"],
            50001: ["chrome-headless-shell", "--remote-debugging-pipe"],
            60000: ["sleep", "10"],
        }

        with mock.patch("weboter.app.server._process_exists", return_value=True), \
             mock.patch("weboter.app.server.Path.iterdir", return_value=proc_entries), \
             mock.patch("weboter.app.server._read_process_stat", side_effect=lambda pid: stats[pid]), \
             mock.patch("weboter.app.server._read_process_cmdline", side_effect=lambda pid: cmdlines[pid]):
            result = list_service_processes(workflow_service)

        self.assertEqual(result["service"]["pid"], self.state.pid)
        self.assertEqual([item["pid"] for item in result["items"]], [43210, 50001])
        self.assertEqual(result["items"][0]["kind"], "service")
        self.assertEqual(result["items"][1]["kind"], "browser")
