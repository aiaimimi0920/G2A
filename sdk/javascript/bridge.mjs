// 出站桥接仅改传输映射；身份、消息、租约及呈现仍由原客户端校验。
import {Client, ProtocolError, validate} from './client.mjs';

export class BridgeClient extends Client {
  constructor(endpoint, {bridgeToken, ...options} = {}) {
    super(endpoint, options);
    this.bridgeToken = bridgeToken;
  }

  async call(path, body = undefined, token = '') {
    let operation, args = {};
    if (path === '/.well-known/g2a.json' && body === undefined) {
      operation = 'describe';
    } else if (path === '/sessions' && body !== undefined) {
      operation = 'join'; args = {request: body};
    } else {
      const match = /^\/sessions\/([A-Za-z0-9._:-]+)\/(?:(events|leave)|actions\/([A-Za-z0-9._:-]+))(?:\?([^#]*))?$/.exec(path);
      if (!match) throw new ProtocolError('invalid_route', 'Unsupported bridge route');
      const [, sid, route, action, query] = match;
      args = {session_id: sid};
      if (route === 'events' && body === undefined) {
        const params = new URLSearchParams(query ?? '');
        const values = params.getAll('cursor');
        const cursor = values[0] ?? '0';
        if ([...params.keys()].some(k => k !== 'cursor') || values.length > 1 || !/^[0-9]{1,10}$/.test(cursor)) {
          throw new ProtocolError('invalid_cursor', 'One nonnegative cursor required');
        }
        operation = 'poll'; args.cursor = Number(cursor);
      } else if (!query && route === 'events' && body !== undefined) {
        operation = 'send'; args.message = body;
      } else if (!query && route === 'leave' && body !== undefined) {
        validate('leave', body);
        operation = 'leave'; args.reason = body.reason;
      } else if (!query && action && body === undefined) {
        operation = 'action'; args.request_id = action;
      } else {
        throw new ProtocolError('invalid_route', 'Unsupported bridge operation');
      }
    }
    const command = validate('bridge_call', {operation, arguments: args, credential: token});
    return super.call('/bridge/call', command, this.bridgeToken);
  }
}
