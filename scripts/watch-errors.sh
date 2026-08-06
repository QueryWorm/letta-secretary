#!/bin/bash
LOGFILE=~/letta/errors.log
MAXSIZE=52428800

rotate() {
  if [ -f "$LOGFILE" ] && [ "$(stat -c%s "$LOGFILE")" -gt "$MAXSIZE" ]; then
    for i in 2 1; do
      [ -f "$LOGFILE.$i" ] && mv -f "$LOGFILE.$i" "$LOGFILE.$((i+1))"
    done
    mv -f "$LOGFILE" "$LOGFILE.1"
  fi
}

touch "$LOGFILE"

(docker logs -f --tail 0 letta-litellm-1 2>&1 & docker logs -f --tail 0 letta-letta-server-1 2>&1 & docker logs -f --tail 0 letta-letta-code-channels-1 2>&1 &) | \
grep --line-buffered -iE "LLMAuthenticationError|LLMRateLimitError|litellm\.(RateLimitError|AuthenticationError)|401|429|Model Group=|llm_authentication|llm_rate_limit" | \
while read -r line; do
  rotate
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $line" >> "$LOGFILE"
done
