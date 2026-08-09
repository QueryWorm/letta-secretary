import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js")
s = p.read_text()

# Anchor: the block after initializeChannels in startLocalChannelGateway.
old = """  const registry2 = getChannelRegistry();
  if (!registry2) {
    client.close();
    throw new Error("Channel registry did not initialize");
  }"""

new = old + """

  // PATCH (letta-secretary): periodically retry starting channels that did
  // not come up (e.g. Telegram API temporarily blocked). Never crashes the
  // gateway and never restarts already-running adapters.
  const retryIntervalMs = Number(process.env.LETTA_CHANNEL_RETRY_INTERVAL_MS || 5 * 60 * 1000);
  if (retryIntervalMs > 0 && options3.channelNames.length > 0) {
    let retryRunning = false;
    const retryChannels = async () => {
      if (retryRunning) return;
      retryRunning = true;
      try {
        for (const channelId of options3.channelNames) {
          try {
            await hydrateChannelAccountSecrets(channelId);
            const accounts = listChannelAccounts(channelId).filter(
              (account) => account.enabled && shouldRestoreChannelAccountForAgentScope(account, options3.restoreAgentScope)
            );
            for (const account of accounts) {
              const adapter = registry2.getAdapter(channelId, account.accountId);
              if (adapter?.isRunning()) continue;
              logChannelStartup(options3.logger, `retrying ${channelId}/${account.accountId} (not running)`);
              try {
                await registry2.startChannelAccount(channelId, account.accountId, { logger: options3.logger });
              } catch (error54) {
                const message = error54 instanceof Error ? error54.message : String(error54);
                console.error(`[Channels] Retry start failed for ${channelId}/${account.accountId}:`, message);
                logChannelStartup(options3.logger, `retry failed ${channelId}/${account.accountId}: ${message}`);
              }
            }
          } catch (error54) {
            const message = error54 instanceof Error ? error54.message : String(error54);
            console.error(`[Channels] Retry sweep failed for ${channelId}:`, message);
          }
        }
      } finally {
        retryRunning = false;
      }
    };
    setInterval(retryChannels, retryIntervalMs);
  }
"""

if old not in s:
    raise SystemExit("ERROR: channel registry init block not found")
p.write_text(s.replace(old, new, 1))
print("OK: channel retry patch applied")
