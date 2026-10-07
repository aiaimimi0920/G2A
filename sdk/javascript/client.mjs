import {randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';

const schema = JSON.parse(readFileSync(new URL('./schema.json', import.meta.url), 'utf8'));
const ajv = new Ajv2020({strict: false, allErrors: false});
const validators = new Map();

export class ProtocolError extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.name = 'ProtocolError';
    this.code = code;
    this.status = status;
  }
}

export function validate(kind, value) {
  if (!schema.$defs[kind]) throw new Error(`Unknown schema kind: ${kind}`);
  if (!validators.has(kind)) {
    validators.set(kind, ajv.compile({$ref: `#/$defs/${kind}`, $defs: schema.$defs}));
  }
  if (!validators.get(kind)(value)) {
    throw new ProtocolError('invalid_message', `Invalid ${kind}`);
  }
  return value;
}

export class Client {
  constructor(endpoint, {expectedGameId, clock = () => performance.now() / 1000, fetchImpl = fetch} = {}) {
    const url = new URL(endpoint);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
      throw new TypeError('An explicit HTTP(S) origin without credentials is required');
    }
    // 不接受别名 IP、localhost 或重定向，将明文限制为调用方显式选定的回环地址。
    if (url.protocol === 'http:' && (!/^http:\/\/127\.0\.0\.1(?::[0-9]+)?\/?$/.test(endpoint))) {
      throw new TypeError('Plain HTTP is restricted to explicit IPv4 loopback');
    }
    if (typeof expectedGameId !== 'string' || !expectedGameId) throw new TypeError('expectedGameId is required');
    this.endpoint = url.origin;
    this.expectedGameId = expectedGameId;
    this.clock = clock;
    this.fetch = fetchImpl;
    this.session = null;
    this.token = null;
    this.cursor = 0;
    this.desktopVisible = null;
    this.desktopBefore = null;
    this.deadline = 0;
  }

  async call(path, body = undefined, token = undefined) {
    const url = new URL(path, this.endpoint);
    if (!path.startsWith('/') || url.origin !== this.endpoint || url.hash) {
      throw new TypeError('Same-origin API path required');
    }
    const headers = {'Content-Type': 'application/json'};
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await this.fetch(url, {
      method: body === undefined ? 'GET' : 'POST', headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      redirect: 'error', signal: AbortSignal.timeout(5000),
    });
    if (!response.body) throw new ProtocolError('transport_error', 'Missing response body', response.status);
    const reader = response.body.getReader();
    const chunks = [];
    let length = 0;
    try {
      for (;;) {
        const {value, done} = await reader.read();
        if (done) break;
        length += value.length;
        if (length > 262144) {
          await reader.cancel();
          throw new ProtocolError('response_too_large', 'Response exceeds client limit');
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
    let result;
    try {
      result = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(Buffer.concat(chunks)));
    } catch {
      throw new ProtocolError('transport_error', 'Peer returned invalid JSON', response.status);
    }
    if (!response.ok) {
      if (typeof result?.error?.code !== 'string' || typeof result?.error?.message !== 'string') {
        throw new ProtocolError('transport_error', 'Peer returned a non-protocol error', response.status);
      }
      throw new ProtocolError(result.error.code, result.error.message, response.status);
    }
    return result;
  }

  async join(invitation, request) {
    if (this.session) throw new ProtocolError('already_joined', 'Create a new client for another session', 409);
    validate('join', request);
    const descriptor = validate('descriptor', await this.call('/.well-known/g2a.json'));
    if (descriptor.game_id !== this.expectedGameId) throw new ProtocolError('wrong_game', 'Descriptor does not match selected game', 409);
    const joined = validate('joined', await this.call('/sessions', request, invitation));
    const s = joined.session;
    if (s.game_id !== this.expectedGameId || s.agent_id !== request.agent_id || s.player_id !== request.player_id) {
      throw new ProtocolError('identity_mismatch', 'Join response changed participant identities', 409);
    }
    this.session = structuredClone(s);
    this.token = joined.session_token;
    this.desktopBefore = request.desktop_visible;
    this.desktopVisible = s.desktop_visible;
    this.lease = joined.lease_seconds;
    this.deadline = this.clock() + this.lease;
    return structuredClone(s);
  }

  requireSession() {
    if (!this.session) throw new ProtocolError('not_joined', 'Join before using session operations', 409);
  }

  async poll() {
    this.requireSession();
    let result;
    try {
      result = validate('poll', await this.call(`/sessions/${this.session.id}/events?cursor=${this.cursor}`, undefined, this.token));
      if (['id', 'game_id', 'agent_id', 'player_id'].some(k => result.session[k] !== this.session[k])) {
        throw new ProtocolError('identity_mismatch', 'Poll response changed session identity', 409);
      }
      let previous = this.cursor;
      for (const event of result.events) {
        if (!Number.isSafeInteger(event.sequence) || event.sequence <= previous || event.sequence > result.cursor) {
          throw new ProtocolError('invalid_cursor', 'Poll response has invalid event ordering', 409);
        }
        previous = event.sequence;
      }
      if (!Number.isSafeInteger(result.cursor) || result.cursor < this.cursor || result.cursor > result.session.sequence) {
        throw new ProtocolError('invalid_cursor', 'Poll cursor is outside snapshot range', 409);
      }
    } catch (error) {
      this.checkLease();
      throw error;
    }
    this.session = structuredClone(result.session);
    this.cursor = result.cursor;
    if (this.session.state === 'closed') this.desktopVisible = this.desktopBefore;
    else {
      this.desktopVisible = this.session.desktop_visible;
      this.deadline = this.clock() + this.lease;
    }
    return result;
  }

  async send(type, data, {messageId = randomUUID()} = {}) {
    this.requireSession();
    const message = validate('message', {id: messageId, type, sender: this.session.agent_id, data});
    // 不以重复收据延长呈现租约，也不自动重试有副作用请求。
    return validate('receipt', await this.call(`/sessions/${this.session.id}/events`, message, this.token));
  }

  checkLease() {
    if (this.session && this.clock() >= this.deadline) {
      this.desktopVisible = this.desktopBefore;
      return true;
    }
    return false;
  }

  async leave(reason = 'user_left') {
    this.requireSession();
    try {
      return validate('session', await this.call(`/sessions/${this.session.id}/leave`, {reason}, this.token));
    } finally {
      this.desktopVisible = this.desktopBefore;
    }
  }
}
