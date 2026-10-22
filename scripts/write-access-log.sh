#!/usr/bin/env bash
# write-access-log.sh — Canonical writer for aes/shadow/access.log with SHA-256 hash chain
# Every write to access.log MUST go through this script.
# Format: TS DOC_ID ACTION PREV_HASH CHAIN_HASH
set -euo pipefail

AES_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCESS_LOG="$AES_ROOT/aes/shadow/access.log"
LOCK_FILE="$AES_ROOT/aes/shadow/.access-log.lock"
GENESIS_HASH="0000000000000000000000000000000000000000000000000000000000000000"

# Usage: write-access-log.sh DOC_ID ACTION [CONTEXT]
if [ $# -lt 2 ]; then
	echo "Usage: $0 DOC_ID ACTION [CONTEXT]" >&2
	echo "  DOC_ID: shadow doc ID (e.g. SD-META-021)" >&2
	echo "  ACTION: action taken (e.g. accessed, created, /synthesis)" >&2
	echo "  CONTEXT: optional context (e.g. ticket ref, phase)" >&2
	exit 1
fi

DOC_ID="$1"
ACTION="$2"
CONTEXT="${3:-}"

# Build the full line content (without hashes)
TS=$(date -Iseconds)
if [ -n "$CONTEXT" ]; then
	LINE_CONTENT="$TS $DOC_ID $ACTION $CONTEXT"
else
	LINE_CONTENT="$TS $DOC_ID $ACTION"
fi

# Acquire lock
exec 9>"$LOCK_FILE"
flock -x 9 || {
	echo "Failed to acquire lock on $LOCK_FILE" >&2
	exit 1
}

# Get previous hash from last line of access.log
PREV_HASH="$GENESIS_HASH"
if [ -f "$ACCESS_LOG" ] && [ -s "$ACCESS_LOG" ]; then
	LAST_LINE=$(tail -1 "$ACCESS_LOG")
	PREV_HASH=$(echo "$LAST_LINE" | awk '{print $NF}')
	if [[ ! "$PREV_HASH" =~ ^[0-9a-f]{64}$ ]]; then
		PREV_HASH="$GENESIS_HASH"
	fi
fi

# Compute chain hash: SHA-256 of "LINE_CONTENT PREV_HASH"
CHAIN_HASH=$(printf "%s %s" "$LINE_CONTENT" "$PREV_HASH" | sha256sum | awk '{print $1}')

# Atomic append: write new line to temp, then append existing log, then rename
TMP_LOG="${ACCESS_LOG}.tmp.$$"
# First copy existing log
cat "$ACCESS_LOG" >"$TMP_LOG" 2>/dev/null || true
# Then append new line
printf "%s %s %s\n" "$LINE_CONTENT" "$PREV_HASH" "$CHAIN_HASH" >>"$TMP_LOG"
# Atomic rename
mv "$TMP_LOG" "$ACCESS_LOG"

# Release lock (auto on exit)
