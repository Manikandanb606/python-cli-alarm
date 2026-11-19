# CLI Alarm Clock

A lightweight, zero-dependency Python CLI alarm clock supporting scheduled alarms, daily repeats, snoozing, and quick countdowns.

## Usage

``````bash
# Quick 10-minute countdown
python alarm.py quick 10 -l "Tea is ready"

# Add a daily alarm
python alarm.py add 06:45 -l "Morning Run" --repeat

# List all alarms
python alarm.py list

# Start the live alarm monitor
python alarm.py start