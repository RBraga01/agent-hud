export function createAgentHudAuditLog({
  sessionId,
  write = console.info,
  record = () => {},
} = {}) {
  if (typeof sessionId !== 'string' || sessionId.length === 0) {
    throw new TypeError('sessionId must be a non-empty string');
  }
  if (typeof write !== 'function') {
    throw new TypeError('write must be a function');
  }
  if (typeof record !== 'function') {
    throw new TypeError('record must be a function');
  }

  return (event, data = {}) => {
    const entry = {
      ...data,
      event,
      session_id: sessionId,
    };
    write('[AgentHUD]', entry);
    record(entry);
  };
}
