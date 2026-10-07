// 本机配对控制面；令牌角色由游戏检查，客户端不自授批准权限。
import {randomUUID} from 'node:crypto';
import {Client, ProtocolError, validate} from './client.mjs';

export class PairingClient {
  constructor(endpoint, {token, expectedGameId, ...options} = {}) {
    this.transport = new Client(endpoint, {expectedGameId, ...options});
    this.token = token;
  }

  call(path, body = undefined) {
    return this.transport.call('/pairing/' + path, body, this.token);
  }

  async discover() {
    return validate('pairing_discovery', await this.call('discovery')).games;
  }

  async request(request, {nonce = randomUUID(), gameInitiated = false} = {}) {
    const body = validate('pairing_request', {nonce, request});
    return validate('pairing_offer', await this.call(gameInitiated ? 'game-request' : 'requests', body));
  }

  async requests() {
    return validate('pairing_page', await this.call('requests')).requests;
  }

  async offer(id) {
    return validate('pairing_offer', await this.call('requests/' + id));
  }

  async decide(offer, {allow, remember = false}) {
    const body = validate('pairing_decision', {scope: offer.scope, allow, remember});
    return validate('pairing_offer', await this.call(`requests/${offer.id}/decision`, body));
  }

  async redeem(id, {desktopVisible}) {
    const body = validate('pairing_redemption', {desktop_visible: desktopVisible});
    const ticket = validate('pairing_ticket', await this.call(`requests/${id}/redeem`, body));
    if (ticket.endpoint !== this.transport.endpoint) {
      throw new ProtocolError('identity_mismatch', 'Pairing ticket changed the selected endpoint', 409);
    }
    const client = new Client(ticket.endpoint, {expectedGameId: this.transport.expectedGameId});
    await client.join(ticket.invitation, ticket.request);
    return client;
  }
}
