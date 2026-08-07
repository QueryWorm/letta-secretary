import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js")
s = p.read_text()

# A) Allow "send_message" in the gateway service command type set
old_a = '"channel_route_remove"\n  ];'
new_a = '"channel_route_remove",\n    "send_message"\n  ];'
if old_a not in s:
    raise SystemExit("ERROR: channel service command types not found")
s = s.replace(old_a, new_a, 1)

# B) Handle "send_message" in the gateway so it can deliver via real adapter
old_b = 'async function executeChannelServiceCommand(command) {\n  if (!isDetachedChannelsCommand(command)) {'
new_b = (
    'async function executeChannelServiceCommand(command) {\n'
    '  if (command && typeof command === "object" && command.type === "send_message") {\n'
    '    const gatewaySendResult = await message_channel({\n'
    '      channel: command.channel,\n'
    '      action: command.action || "send",\n'
    '      message: command.message ?? command.text,\n'
    '      chat_id: command.chat_id ?? command.chatId,\n'
    '      target: command.target,\n'
    '      thread_id: command.thread_id ?? command.threadId,\n'
    '      account_id: command.account_id ?? command.accountId,\n'
    '      parentScope: command.parentScope,\n'
    '      channelTurnSources: command.channelTurnSources\n'
    '    });\n'
    '    return [{ type: "send_message_response", result: gatewaySendResult }];\n'
    '  }\n'
    '  if (!isDetachedChannelsCommand(command)) {'
)
if old_b not in s:
    raise SystemExit("ERROR: executeChannelServiceCommand block not found")
s = s.replace(old_b, new_b, 1)

# C) Delegate from main process (cron turns) to the gateway via IPC
old_c = (
    'async function message_channel(args) {\n'
    '  if (!getChannelRegistry()) {\n'
    '    return "Error: Channel system is not initialized. Start with --channels flag.";\n'
    '  }\n'
    '  if (!args.parentScope) {'
)
new_c = (
    'async function message_channel(args) {\n'
    '  if (!getChannelRegistry()) {\n'
    '    const gatewaySupervisor = globalThis.__lettaChannelGatewaySupervisor;\n'
    '    if (gatewaySupervisor && args && args.parentScope) {\n'
    '      try {\n'
    '        const gatewayResponse = await gatewaySupervisor.request({\n'
    '          kind: "protocol",\n'
    '          command: {\n'
    '            type: "send_message",\n'
    '            channel: args.channel,\n'
    '            action: args.action,\n'
    '            message: args.message ?? args.text,\n'
    '            chat_id: args.chat_id ?? args.chatId,\n'
    '            target: args.target,\n'
    '            thread_id: args.thread_id ?? args.threadId,\n'
    '            account_id: args.account_id ?? args.accountId,\n'
    '            parentScope: args.parentScope,\n'
    '            channelTurnSources: args.channelTurnSources\n'
    '          }\n'
    '        });\n'
    '        const gatewayResult = gatewayResponse && gatewayResponse.messages && gatewayResponse.messages[0] ? gatewayResponse.messages[0].result : undefined;\n'
    '        return gatewayResult ?? "Message delivered via channel gateway.";\n'
    '      } catch (gatewayError) {\n'
    '        return "Error sending message via channel gateway: " + (gatewayError instanceof Error ? gatewayError.message : String(gatewayError));\n'
    '      }\n'
    '    }\n'
    '    return "Error: Channel system is not initialized. Start with --channels flag.";\n'
    '  }\n'
    '  if (!args.parentScope) {'
)
if old_c not in s:
    raise SystemExit("ERROR: message_channel block not found")
s = s.replace(old_c, new_c, 1)

# D) Expose the gateway supervisor to the main process
old_d = '        });\n        runtime.serviceCommandHandler = (request) => {'
new_d = '        });\n        globalThis.__lettaChannelGatewaySupervisor = channelGatewaySupervisor;\n        runtime.serviceCommandHandler = (request) => {'
if old_d not in s:
    raise SystemExit("ERROR: serviceCommandHandler block not found")
s = s.replace(old_d, new_d, 1)

p.write_text(s)
print("OK: gateway send_message IPC patches applied")
