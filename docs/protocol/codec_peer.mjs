// 独立 JavaScript 对照实现；仅验证草案编码，不提供认证、签名或生产网络绑定。
import { createHash } from 'node:crypto';

const limits = { bytes: 1048576, depth: 32, nodes: 65536, items: 4096, string: 65536 };
const domains = new Set(['scope', 'control', 'message', 'result', 'relay', 'auto-rule',
  'join-intent', 'action-arguments', 'action-definition']);
const fail = (code) => { throw new Error(code); };

function checkString(value) {
  for (const char of value) {
    const point = char.codePointAt(0);
    if (point >= 0xd800 && point <= 0xdfff) fail('invalid_unicode');
  }
  if (Buffer.byteLength(value) > limits.string) fail('string_limit');
}

function scalarOrder(left, right) {
  const a = [...left].map(c => c.codePointAt(0)), b = [...right].map(c => c.codePointAt(0));
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return a.length - b.length;
}

export function canonical(value) {
  let nodes = 0, size = 0;
  const parts = [];
  function emit(text) {
    size += Buffer.byteLength(text);
    if (size > limits.bytes) fail('byte_limit');
    parts.push(text);
  }
  function walk(item, depth) {
    if (++nodes > limits.nodes) fail('node_limit');
    if (item === null || typeof item === 'boolean') return emit(String(item));
    if (typeof item === 'string') { checkString(item); return emit(JSON.stringify(item)); }
    if (typeof item === 'number') {
      if (!Number.isSafeInteger(item)) fail('integer_out_of_range');
      if (Object.is(item, -0)) fail('invalid_number');
      return emit(String(item));
    }
    if (typeof item !== 'object' || (Object.getPrototypeOf(item) !== Object.prototype &&
        Object.getPrototypeOf(item) !== null && !Array.isArray(item))) fail('invalid_type');
    if (depth >= limits.depth) fail('depth_limit');
    const array = Array.isArray(item), keys = array ? [...item.keys()] : Object.keys(item).sort(scalarOrder);
    if (keys.length > limits.items) fail('container_limit');
    emit(array ? '[' : '{');
    keys.forEach((key, index) => {
      if (index) emit(',');
      if (!array) { walk(key, depth + 1); emit(':'); }
      walk(item[key], depth + 1);
    });
    emit(array ? ']' : '}');
  }
  walk(value, 0);
  return Buffer.from(parts.join(''), 'utf8');
}

export function decode(raw) {
  if (!Buffer.isBuffer(raw)) fail('bytes_required');
  if (raw.length > limits.bytes) fail('byte_limit');
  if (raw.subarray(0, 3).equals(Buffer.from([239, 187, 191]))) fail('bom_forbidden');
  let text;
  try { text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(raw); }
  catch { fail('invalid_utf8'); }
  let offset = 0, nodes = 0;
  const ws = () => { while (offset < text.length && /[\x20\t\r\n]/.test(text[offset])) offset++; };
  function string() {
    const start = offset++;
    while (offset < text.length) {
      const char = text[offset++];
      if (char === '\\') offset++;
      else if (char === '"') {
        let result;
        try { result = JSON.parse(text.slice(start, offset)); } catch { fail('invalid_json'); }
        checkString(result);
        return result;
      }
    }
    fail('invalid_json');
  }
  function value(depth) {
    ws();
    if (++nodes > limits.nodes) fail('node_limit');
    const char = text[offset];
    if (char === '"') return string();
    if (char === '{' || char === '[') {
      if (depth >= limits.depth) fail('depth_limit');
      const array = char === '[', end = array ? ']' : '}';
      const result = array ? [] : Object.create(null);
      offset++; ws();
      if (text[offset] === end) { offset++; return result; }
      let count = 0;
      while (true) {
        if (++count > limits.items) fail('container_limit');
        if (array) result.push(value(depth + 1));
        else {
          ws();
          if (text[offset] !== '"') fail('invalid_json');
          if (++nodes > limits.nodes) fail('node_limit');
          const key = string();
          if (Object.hasOwn(result, key)) fail('duplicate_key');
          ws(); if (text[offset++] !== ':') fail('invalid_json');
          result[key] = value(depth + 1);
        }
        ws();
        if (text[offset] === end) { offset++; return result; }
        if (text[offset++] !== ',') fail('invalid_json');
      }
    }
    for (const [literal, item] of [['true', true], ['false', false], ['null', null]]) {
      if (text.startsWith(literal, offset)) { offset += literal.length; return item; }
    }
    const match = /^(?:-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|-?Infinity|NaN)/.exec(text.slice(offset));
    if (!match) fail('invalid_json');
    const token = match[0]; offset += token.length;
    if (token === '-0' || /[.eEIN]/.test(token)) fail('invalid_number');
    const number = Number(token);
    if (!Number.isSafeInteger(number)) fail('integer_out_of_range');
    return number;
  }
  const result = value(0); ws();
  if (offset !== text.length) fail('invalid_json');
  return result;
}

export function digest(domain, value) {
  if (!domains.has(domain)) fail('invalid_digest_domain');
  return createHash('sha256').update(`g2a-cjson-1\0${domain}\0`, 'ascii').update(canonical(value)).digest('hex');
}
