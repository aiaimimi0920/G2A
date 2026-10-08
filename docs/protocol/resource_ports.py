"""受控传输、声明式 fixture 解析和 Renderer 能力假端口；不发网络请求或执行资源代码。"""

from copy import deepcopy
from hashlib import sha256
from ipaddress import ip_address
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit


MEDIA = "application/vnd.g2a.fixture-avatar+json"
FORMAT = "fixture-1"
PROFILE = ("fixture-avatar", "1")


class ResourcePorts:
    def __init__(self, checks, relations, issuer):
        self.C, self.R = checks, relations
        self.responses, self.trace, self.renderer_profiles = {}, [], {}
        self.allowed_claims = {(checks.codec.canonical(issuer), "fixture-only")}
        self.parser_revision, self.policy_revision = "fixture-parser-1", "fixture-policy-1"
        self.parse_calls = 0
        self.after_prepare = None  # 可信调度注入点；不是可从 wire 提交的回调。

    def policy_key(self, policy):
        material = {"policy": policy, "revision": self.policy_revision,
                    "claims": sorted([[issuer.decode("utf-8"), claim] for issuer, claim in self.allowed_claims])}
        return sha256(b"fixture-resource-policy-v1\0" + self.C.codec.canonical(material)).hexdigest()

    def cache_key(self, manifest, policy):
        material = {"manifest": manifest, "policy": self.policy_key(policy), "parser": self.parser_revision}
        return sha256(b"fixture-resource-cache-v1\0" + self.C.codec.canonical(material)).hexdigest()

    def _origin(self, url):
        require = self.R.require
        require(isinstance(url, str) and not any(ord(c) <= 32 or c == "\\" for c in url), "resource_policy_denied")
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            raise self.C.ContractError("resource_policy_denied") from None
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.fragment,
                "resource_policy_denied")
        host = parsed.hostname.lower()
        return "https://" + ("[" + host + "]" if ":" in host else host) + (":" + str(port) if port not in (None, 443) else "")

    def _fetch(self, manifest, policy):
        require = self.R.require
        response = self.responses.get(manifest["locator"])
        require(response is not None, "temporarily_unavailable")
        require(type(response) is dict, "resource_policy_denied")
        require(response.get("status", "ok") == "ok", "temporarily_unavailable")
        hops = response.get("hops", [])
        require(type(hops) is list and 0 < len(hops) <= 8, "resource_policy_denied")
        require(all(type(hop) is dict and {"url", "tls_verified", "resolved", "connected_ip"} <= hop.keys() for hop in hops),
                "resource_policy_denied")
        require(hops[0]["url"] == manifest["locator"], "resource_policy_denied")
        for index, hop in enumerate(hops):
            origin = self._origin(hop["url"])
            require(origin in policy["approved_origins"] and origin in manifest["approved_origins"], "resource_policy_denied")
            require(hop.get("tls_verified") is True, "resource_policy_denied")
            resolved = hop.get("resolved", [])
            require(type(resolved) is list and 0 < len(resolved) <= 16 and all(type(value) is str for value in resolved) and
                    type(hop["connected_ip"]) is str, "resource_policy_denied")
            try:
                addresses = [ip_address(value) for value in resolved]
                connected = ip_address(hop["connected_ip"])
            except (ValueError, KeyError, TypeError):
                raise self.C.ContractError("resource_policy_denied") from None
            require(connected in addresses, "resource_policy_denied")
            for address in addresses:
                address = getattr(address, "ipv4_mapped", None) or address
                require(not address.is_multicast and not address.is_unspecified and
                        (address.is_global or policy["allow_private_network"]), "resource_policy_denied")
            require(hop.get("redirect_to") == (hops[index + 1]["url"] if index + 1 < len(hops) else None), "resource_policy_denied")
            # 只有批准的 URL 和媒体类型；不接收会话凭据/header/cookie 参数。
            self.trace.append({"url": hop["url"], "connected_ip": str(connected), "headers": {"Accept": manifest["media_type"]}})
        pieces, size = [], 0
        chunks = response.get("chunks", [])
        require(type(chunks) is list and len(chunks) <= 4096, "resource_limit")
        for chunk in chunks:
            require(type(chunk) is bytes, "resource_integrity_error")
            size += len(chunk)
            require(size <= manifest["byte_size"] and size <= policy["max_total_bytes"], "resource_limit")
            pieces.append(chunk)
        raw = b"".join(pieces)
        require(size == manifest["byte_size"] and sha256(raw).hexdigest() == manifest["content_digest"], "resource_integrity_error")
        return raw

    def _parse(self, raw, manifest, policy):
        require = self.R.require
        self.parse_calls += 1
        require(manifest["media_type"] == MEDIA and manifest["format_version"] == FORMAT, "avatar_incompatible")
        require(set(manifest["sandbox_requirements"]) <= {"declarative-only", "no-execution"}, "resource_policy_denied")
        try:
            value = self.C.codec.decode(raw)
        except self.C.codec.CodecError:
            raise self.C.ContractError("resource_integrity_error") from None
        require(type(value) is dict and set(value) == {"fixture_format", "compatibility", "dependencies", "entries", "model"}, "resource_integrity_error")
        require(value["fixture_format"] == FORMAT and
                self.C.codec.canonical(value["compatibility"]) == self.C.codec.canonical(manifest["compatibility"]), "avatar_incompatible")
        require(value["dependencies"] == sorted(child["content_digest"] for child in manifest["dependency_manifests"]), "resource_integrity_error")
        require(type(value["model"]) is dict and set(value["model"]) == {"label"} and type(value["model"]["label"]) is str,
                "resource_integrity_error")
        entries = value["entries"]
        require(type(entries) is list and len(entries) <= 128, "resource_limit")
        seen, unpacked = set(), 0
        for entry in entries:
            require(type(entry) is dict and set(entry) == {"path", "kind", "content"} and entry["kind"] == "file", "resource_policy_denied")
            path = entry["path"]
            require(type(path) is str and path and not any(ord(c) < 32 or c in "\\:" for c in path), "resource_policy_denied")
            require(not PurePosixPath(path).is_absolute() and not PureWindowsPath(path).drive and
                    all(part not in {"", ".", ".."} for part in path.split("/")) and path not in seen, "resource_policy_denied")
            require(PurePosixPath(path).suffix in {".txt", ".json"} and type(entry["content"]) is str, "resource_policy_denied")
            seen.add(path)
            unpacked += len(entry["content"].encode("utf-8"))
            require(unpacked <= policy["max_unpacked_bytes"], "resource_limit")
        return {"model": deepcopy(value["model"]), "unpacked_bytes": unpacked}

    def prepare(self, manifest, policy, cache):
        """整棵闭包只写暂存区；全部验证成功才交给 authority 原子发布。"""
        self.R.validate_manifest_closure(manifest, policy, supported_profiles={PROFILE})
        staged, visited, total_unpacked = {}, set(), 0
        def visit(item):
            nonlocal total_unpacked
            key = self.cache_key(item, policy)
            if key in visited:
                return
            visited.add(key)
            self.R.require((self.C.codec.canonical(item["issuer"]), item["license_claim"]) in self.allowed_claims, "resource_policy_denied")
            for dependency in item["dependency_manifests"]:
                visit(dependency)
            existing = cache.get(key)
            if existing is None:
                parsed = self._parse(self._fetch(item, policy), item, policy)
                receipt = {"asset_id": item["asset_id"], "content_digest": item["content_digest"], "validation_receipt": "asset-proof-" + key,
                           "parser_revision": self.parser_revision, "policy_revision": self.policy_revision}
                existing = {"receipt": receipt, "parsed": parsed}
            total_unpacked += existing["parsed"]["unpacked_bytes"]
            self.R.require(total_unpacked <= policy["max_unpacked_bytes"], "resource_limit")
            staged[key] = deepcopy(existing)
        visit(manifest)
        if self.after_prepare is not None:
            callback, self.after_prepare = self.after_prepare, None
            callback()
        return staged

    def renderer_accepts(self, manifest, device):
        """独立于解析器的固定 Renderer 能力登记，不把解析成功等同于设备可渲染。"""
        profiles = self.renderer_profiles.get(device or "fixture-headless", set())
        def accepts(item):
            key = (item["compatibility"]["profile"], item["compatibility"]["revision"])
            return key in profiles and all(accepts(child) for child in item["dependency_manifests"])
        return accepts(manifest)
