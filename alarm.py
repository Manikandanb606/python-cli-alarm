#!/usr/bin/env python3
"""A lightweight, zero-dependency Python CLI Alarm Clock."""

import argparse
import datetime
import json
import os
import platform
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

DATA_FILE = Path.home() / ".cli_alarms.json"


# ---------------------------------------------------------------------------
# Storage Helpers (JSON file, no database)
# ---------------------------------------------------------------------------

def load_alarms() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_alarms(alarms: list[dict]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(alarms, f, indent=2)


# ---------------------------------------------------------------------------
# Audio & Terminal Alert
# ---------------------------------------------------------------------------

def trigger_sound() -> None:
    """Plays an alert sound using native OS capabilities or terminal bell."""
    system = platform.system()
    try:
        if system == "Windows":
            import winsound
            winsound.Beep(1000, 500)
        elif system == "Darwin":
            subprocess.run(
                ["afplay", "/System/Library/Sounds/Ping.aiff"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            # Linux / Unix fallback: terminal bell + paplay/aplay if available
            sys.stdout.write("\a")
            sys.stdout.flush()
    except Exception:
        sys.stdout.write("\a")
        sys.stdout.flush()


def ring_alarm(alarm: dict, snooze_minutes: int = 5) -> str:
    """
    Blocks until the user dismisses or snoozes the ringing alarm.
    Returns 'dismissed' or 'snoozed'.
    """
    stop_ringing = threading.Event()

    def beep_loop():
        while not stop_ringing.is_set():
            trigger_sound()
            stop_ringing.wait(1.0)

    t = threading.Thread(target=beep_loop, daemon=True)
    t.start()

    label = alarm.get("label") or "Alarm"
    print("\n" + "=" * 50)
    print(f"⏰  ALARM RINGING! [{alarm['time']}] - {label}")
    print("=" * 50)
    print(f"Press [ENTER] to dismiss, or type 's' + [ENTER] to snooze ({snooze_minutes}m): ", end="", flush=True)

    try:
        choice = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = ""
    finally:
        stop_ringing.set()
        t.join(timeout=1.5)

    if choice.startswith("s"):
        return "snoozed"
    return "dismissed"


# ---------------------------------------------------------------------------
# Time Parsing & Scheduling Logic
# ---------------------------------------------------------------------------

def parse_time_str(time_str: str) -> tuple[int, int]:
    """Parses 'HH:MM' (24h) or 'HH:MM AM/PM' into (hour, minute)."""
    time_str = time_str.strip().upper()
    formats = ["%H:%M", "%I:%M %p", "%I:%M%p"]
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(time_str, fmt)
            return dt.hour, dt.minute
        except ValueError:
            continue
    raise ValueError(f"Invalid time format: '{time_str}'. Use HH:MM (24h) or HH:MM AM/PM.")


def get_next_trigger(hour: int, minute: int, now: datetime.datetime) -> datetime.datetime:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return target


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def cmd_add(args: argparse.Namespace) -> None:
    try:
        hour, minute = parse_time_str(args.time)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    alarms = load_alarms()
    alarm_id = uuid.uuid4().hex[:6]
    formatted_time = f"{hour:02d}:{minute:02d}"

    new_alarm = {
        "id": alarm_id,
        "time": formatted_time,
        "hour": hour,
        "minute": minute,
        "label": args.label or "Alarm",
        "repeat": args.repeat,
        "enabled": True,
        "snooze_until": None,
    }
    alarms.append(new_alarm)
    save_alarms(alarms)

    repeat_tag = " (Daily)" if args.repeat else " (One-time)"
    print(f"Added alarm [{alarm_id}] for {formatted_time} - '{new_alarm['label']}'{repeat_tag}")


def cmd_list(_args: argparse.Namespace) -> None:
    alarms = load_alarms()
    if not alarms:
        print("No alarms configured. Use `add HH:MM` to create one.")
        return

    print(f"{'ID':<8} {'TIME':<8} {'STATUS':<10} {'MODE':<10} {'LABEL'}")
    print("-" * 55)
    for a in alarms:
        status = "ENABLED" if a.get("enabled") else "DISABLED"
        if a.get("snooze_until"):
            status = f"SNOOZED"
        mode = "Daily" if a.get("repeat") else "Once"
        print(f"{a['id']:<8} {a['time']:<8} {status:<10} {mode:<10} {a['label']}")


def cmd_delete(args: argparse.Namespace) -> None:
    alarms = load_alarms()
    updated = [a for a in alarms if a["id"] != args.id]
    if len(updated) == len(alarms):
        print(f"Alarm ID '{args.id}' not found.", file=sys.stderr)
        sys.exit(1)
    save_alarms(updated)
    print(f"Deleted alarm [{args.id}].")


def cmd_toggle(args: argparse.Namespace) -> None:
    alarms = load_alarms()
    found = False
    for a in alarms:
        if a["id"] == args.id:
            a["enabled"] = not a["enabled"]
            a["snooze_until"] = None
            state = "enabled" if a["enabled"] else "disabled"
            print(f"Alarm [{args.id}] ({a['time']}) is now {state}.")
            found = True
            break
    if not found:
        print(f"Alarm ID '{args.id}' not found.", file=sys.stderr)
        sys.exit(1)
    save_alarms(alarms)


def cmd_quick(args: argparse.Namespace) -> None:
    """Starts an immediate countdown timer/alarm for N minutes or until HH:MM."""
    now = datetime.datetime.now()
    if args.target.isdigit():
        minutes = int(args.target)
        target_dt = now + datetime.timedelta(minutes=minutes)
    else:
        try:
            hour, minute = parse_time_str(args.target)
            target_dt = get_next_trigger(hour, minute, now)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    alarm = {
        "id": "quick",
        "time": target_dt.strftime("%H:%M:%S"),
        "label": args.label or "Quick Alarm",
    }

    print(f"Quick alarm set for {target_dt.strftime('%Y-%m-%d %H:%M:%S')} ({alarm['label']}).")
    print("Press Ctrl+C to cancel.\n")

    try:
        while True:
            now = datetime.datetime.now()
            remaining = (target_dt - now).total_seconds()
            if remaining <= 0:
                print("\r" + " " * 40 + "\r", end="")
                action = ring_alarm(alarm, snooze_minutes=args.snooze)
                if action == "snoozed":
                    target_dt = datetime.datetime.now() + datetime.timedelta(minutes=args.snooze)
                    alarm["time"] = target_dt.strftime("%H:%M:%S")
                    print(f"Snoozed until {alarm['time']}...")
                    continue
                print("Alarm dismissed.")
                break

            hrs, rem = divmod(int(remaining), 3600)
            mins, secs = divmod(rem, 60)
            sys.stdout.write(f"\rTime remaining: {hrs:02d}:{mins:02d}:{secs:02d} ")
            sys.stdout.flush()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nQuick alarm cancelled.")


def cmd_start(args: argparse.Namespace) -> None:
    """Runs the foreground clock daemon that monitors all saved alarms."""
    print("Alarm clock daemon running. Press Ctrl+C to stop.")
    triggered_minute_tracker: set[tuple[str, str]] = set()

    try:
        while True:
            now = datetime.datetime.now()
            current_hhmm = now.strftime("%H:%M")
            current_date_min = now.strftime("%Y-%m-%d %H:%M")

            alarms = load_alarms()
            modified = False

            for alarm in alarms:
                if not alarm.get("enabled"):
                    continue

                alarm_id = alarm["id"]
                snooze_until = alarm.get("snooze_until")

                is_due = False
                if snooze_until:
                    snooze_dt = datetime.datetime.fromisoformat(snooze_until)
                    if now >= snooze_dt:
                        is_due = True
                elif alarm["time"] == current_hhmm and (alarm_id, current_date_min) not in triggered_minute_tracker:
                    is_due = True

                if is_due:
                    triggered_minute_tracker.add((alarm_id, current_date_min))
                    action = ring_alarm(alarm, snooze_minutes=args.snooze)

                    if action == "snoozed":
                        next_snooze = datetime.datetime.now() + datetime.timedelta(minutes=args.snooze)
                        alarm["snooze_until"] = next_snooze.isoformat()
                        print(f"Snoozed [{alarm_id}] for {args.snooze} minutes (until {next_snooze.strftime('%H:%M:%S')}).")
                    else:
                        alarm["snooze_until"] = None
                        if not alarm.get("repeat"):
                            alarm["enabled"] = False
                        print(f"Dismissed [{alarm_id}].")

                    modified = True

            if modified:
                save_alarms(alarms)

            # Live clock status line
            active_count = sum(1 for a in alarms if a.get("enabled"))
            sys.stdout.write(f"\r[{now.strftime('%H:%M:%S')}] Active alarms: {active_count} ")
            sys.stdout.flush()
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nAlarm daemon stopped.")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="alarm",
        description="Lightweight Python CLI Alarm Clock",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = subparsers.add_parser("add", help="Add a new scheduled alarm")
    p_add.add_argument("time", help="Alarm time in HH:MM (24h) or 'HH:MM AM/PM'")
    p_add.add_argument("-l", "--label", default="Alarm", help="Label for the alarm")
    p_add.add_argument("-r", "--repeat", action="store_true", help="Repeat daily")
    p_add.set_defaults(func=cmd_add)

    # list
    p_list = subparsers.add_parser("list", help="List all configured alarms")
    p_list.set_defaults(func=cmd_list)

    # delete
    p_del = subparsers.add_parser("delete", help="Delete an alarm by ID")
    p_del.add_argument("id", help="Alarm ID")
    p_del.set_defaults(func=cmd_delete)

    # toggle
    p_tog = subparsers.add_parser("toggle", help="Enable or disable an alarm by ID")
    p_tog.add_argument("id", help="Alarm ID")
    p_tog.set_defaults(func=cmd_toggle)

    # quick
    p_quick = subparsers.add_parser("quick", help="Set a quick one-off countdown or time alarm")
    p_quick.add_argument("target", help="Minutes from now (e.g. '15') or target time (e.g. '07:30')")
    p_quick.add_argument("-l", "--label", default="Quick Alarm", help="Label for the alarm")
    p_quick.add_argument("-s", "--snooze", type=int, default=5, help="Snooze duration in minutes (default: 5)")
    p_quick.set_defaults(func=cmd_quick)

    # start
    p_start = subparsers.add_parser("start", help="Start the live clock & alarm monitor")
    p_start.add_argument("-s", "--snooze", type=int, default=5, help="Default snooze duration in minutes (default: 5)")
    p_start.set_defaults(func=cmd_start)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()