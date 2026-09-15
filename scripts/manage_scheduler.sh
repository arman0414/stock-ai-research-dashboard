#!/usr/bin/env bash
# Manage the macOS launchd job that runs the daily prediction/evaluation
# cycle (scripts/run_daily_cycle.py) automatically on market days.
#
# This script never embeds secrets. The launchd job invokes the project's
# venv python directly against run_daily_cycle.py, which loads credentials
# itself from the project's existing .env file (see stock_ai/config.py) --
# the exact same mechanism used for manual/local runs.
#
# Usage:
#   scripts/manage_scheduler.sh install     Generate the .plist and load it
#   scripts/manage_scheduler.sh status      Show whether the job is loaded and last run info
#   scripts/manage_scheduler.sh run-now     Trigger one run immediately (for testing)
#   scripts/manage_scheduler.sh disable     Unload the job (stops future scheduled runs)
#   scripts/manage_scheduler.sh enable      Re-load a previously installed job
#   scripts/manage_scheduler.sh uninstall   Unload the job and remove the .plist
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.stockai.dailycycle"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$PROJECT_ROOT/var/logs"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
RUN_SCRIPT="$PROJECT_ROOT/scripts/run_daily_cycle.py"

# Default schedule: 21:30 local time, Monday-Friday. US markets close at
# 16:00 ET / 13:00 PT; 21:30 local (assuming a US timezone) leaves a wide
# safety margin for the data provider's end-of-day bar to be finalized.
# Weekends are skipped by StartCalendarInterval's Weekday entries below;
# market holidays are handled naturally at the application level (see
# docs/DAILY_AUTOMATION.md) rather than in the scheduler itself, since
# run_daily_cycle derives its "as of" date from the latest stored price
# bar, not from the calendar day the job happened to fire on.
HOUR="${STOCK_AI_SCHEDULE_HOUR:-21}"
MINUTE="${STOCK_AI_SCHEDULE_MINUTE:-30}"

usage() {
    echo "Usage: $0 {install|status|run-now|disable|enable|uninstall}" >&2
    exit 1
}

require_plist() {
    if [[ ! -f "$PLIST_PATH" ]]; then
        echo "No scheduler installed at $PLIST_PATH. Run '$0 install' first." >&2
        exit 1
    fi
}

cmd_install() {
    if [[ ! -x "$PYTHON_BIN" ]]; then
        echo "error: venv python not found at $PYTHON_BIN -- create the venv first." >&2
        exit 1
    fi
    mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

    cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${RUN_SCRIPT}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>

    <!-- No secrets here. run_daily_cycle.py -> stock_ai.config.get_settings()
         loads ${PROJECT_ROOT}/.env itself at runtime, the same way a manual
         "python3 scripts/run_daily_cycle.py" run does. -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/bin:/bin:/usr/sbin:/sbin:${PROJECT_ROOT}/.venv/bin</string>
    </dict>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>${HOUR}</integer><key>Minute</key><integer>${MINUTE}</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>${HOUR}</integer><key>Minute</key><integer>${MINUTE}</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>${HOUR}</integer><key>Minute</key><integer>${MINUTE}</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>${HOUR}</integer><key>Minute</key><integer>${MINUTE}</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>${HOUR}</integer><key>Minute</key><integer>${MINUTE}</integer></dict>
    </array>

    <!-- If the Mac is asleep at the scheduled time, launchd runs the job
         as soon as the Mac wakes (StartCalendarInterval semantics), rather
         than skipping the day silently. -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/scheduler.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/scheduler.err.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST

    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"
    echo "Installed and loaded $LABEL (${HOUR}:$(printf '%02d' "$MINUTE") local time, Mon-Fri)."
    echo "Plist: $PLIST_PATH"
    echo "Logs:  $LOG_DIR/daily_cycle.log (application log), $LOG_DIR/scheduler.out.log / scheduler.err.log (launchd stdio)"
}

cmd_status() {
    require_plist
    echo "Plist: $PLIST_PATH"
    if launchctl list "$LABEL" >/dev/null 2>&1; then
        echo "State: loaded"
        launchctl list "$LABEL"
    else
        echo "State: not loaded (disabled)"
    fi
    echo
    if [[ -f "$LOG_DIR/daily_cycle.log" ]]; then
        echo "Last application log lines:"
        tail -n 5 "$LOG_DIR/daily_cycle.log"
    else
        echo "No application log yet at $LOG_DIR/daily_cycle.log"
    fi
}

cmd_run_now() {
    require_plist
    launchctl start "$LABEL"
    echo "Triggered $LABEL manually. Check status with '$0 status' or tail $LOG_DIR/daily_cycle.log"
}

cmd_disable() {
    require_plist
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    echo "Disabled $LABEL (plist kept at $PLIST_PATH; future scheduled runs will not fire until re-enabled)."
}

cmd_enable() {
    require_plist
    launchctl load "$PLIST_PATH"
    echo "Enabled $LABEL."
}

cmd_uninstall() {
    if [[ -f "$PLIST_PATH" ]]; then
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        rm -f "$PLIST_PATH"
        echo "Uninstalled $LABEL."
    else
        echo "Nothing to uninstall at $PLIST_PATH."
    fi
}

case "${1:-}" in
    install) cmd_install ;;
    status) cmd_status ;;
    run-now) cmd_run_now ;;
    disable) cmd_disable ;;
    enable) cmd_enable ;;
    uninstall) cmd_uninstall ;;
    *) usage ;;
esac
