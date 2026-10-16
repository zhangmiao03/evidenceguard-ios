"""Persistent, fail-closed dispatcher. No SDK import or official secret on the server."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import hmac
import base64
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid

from .catalog import TOOLS, FIELDS, MATRIX, ToolError, check, support
from .verification import variant, scope, reference_baselines, check_frame


def uid(prefix):
    return prefix + "_" + uuid.uuid4().hex


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def require(condition, code, message, status=409):
    if not condition:
        raise ToolError(code, message, status)


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS records(kind TEXT,id TEXT,team TEXT,body TEXT,PRIMARY KEY(kind,id))")
        self.db.execute("CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at REAL,team TEXT,actor TEXT,event TEXT,ref TEXT)")
        self.lock = threading.RLock()

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                yield
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def put(self, kind, item):
        self.db.execute("INSERT OR REPLACE INTO records VALUES(?,?,?,?)", (kind, item["id"], item["team"], json.dumps(item, ensure_ascii=False)))
        return item

    def get(self, kind, key):
        row = self.db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        require(row is not None, "NOT_FOUND", "Record not found", 404)
        return json.loads(row[0])

    def all(self, kind, team):
        return [json.loads(row[0]) for row in self.db.execute("SELECT body FROM records WHERE kind=? AND team=?", (kind, team))]

    def audit(self, principal, event, ref):
        # No tokens, official identities, payloads or frame data in audit messages.
        self.db.execute("INSERT INTO audit(at,team,actor,event,ref) VALUES(?,?,?,?,?)", (time.time(), principal["team"], principal["id"], event, ref))


class Runtime:
    def __init__(self, db_path, principals, demo=False, clock=time.time, policy="competition"):
        self.store = Store(db_path)
        self.principals = principals
        self.demo = demo
        self.clock = clock
        self.media_root = Path(db_path).parent / (Path(db_path).stem + "-media")
        require(policy in ("competition", "bounded"), "UNSUPPORTED_PARAMETER", "Unknown execution policy")
        self.policy = policy

    def auth(self, bearer):
        for principal in self.principals:
            if bearer and hmac.compare_digest(principal["token"], bearer):
                return {key: value for key, value in principal.items() if key != "token"}
        raise ToolError("UNAUTHENTICATED", "A valid access token is required", 401)

    def role(self, p, *roles):
        require(p["role"] in roles, "PERMISSION_DENIED", "Role does not permit this action", 403)

    def scoped(self, p, item):
        require(item["team"] == p["team"], "PERMISSION_DENIED", "Record outside team", 403)
        device_id = item.get("deviceId", item.get("id") if item.get("model") else None)
        require(device_id is None or device_id in p.get("devices", []), "PERMISSION_DENIED", "Device outside grant", 403)
        if item.get("taskId"):
            require(item["taskId"] in p.get("tasks", []), "PERMISSION_DENIED", "Task outside grant", 403)
        return item

    def device(self, p, device_id):
        return self.scoped(p, self.store.get("device", device_id))

    def record(self, p, kind, key):
        return self.scoped(p, self.store.get(kind, key))

    def tools(self, p):
        granted = [value for key, value in TOOLS.items() if key in p.get("tools", TOOLS)]
        if p["role"] != "agent":
            return granted
        local = {"devices_list", "device_inspect", "operation_get", "operation_cancel", "camera_stop", "camera_evidence_get"}
        devices = [d for d in self.store.all("device", p["team"]) if d["id"] in p.get("devices", [])]
        validations = self.store.all("validation", p["team"])
        return [tool for tool in granted if tool["name"] in local or any(
            tool["name"] in d["routes"] and d["routes"][tool["name"]].get("ready") is True
            and support(tool["capabilities"][0], d["executorPlatform"], d["model"]) in ("A", "I", "W", "S")
            and (self.demo or any(v["deviceId"] == d["id"] and v["tool"] == tool["name"] and v["status"] == "passed" and v["capabilityRevision"] == d["capabilityRevision"] for v in validations))
            for d in devices)]

    def _expire(self, team):
        now = self.clock()
        for op in self.store.all("operation", team):
            if op["deadline"] >= now:
                continue
            if op["executionState"] in ("queued", "awaitingApproval"):
                op.update(executionState="failed", error={"code": "DEADLINE_EXCEEDED", "message": "Command expired before dispatch"})
            elif op["executionState"] in ("executing", "verifying"):
                op.update(executionState="unknown", error={"code": "DISPATCH_UNKNOWN", "message": "Deadline elapsed after dispatch; no automatic retry"})
            else:
                continue
            self.store.put("operation", op)

    def snapshot(self, p):
        with self.store.transaction():
            self._expire(p["team"])
            devices = [d for d in self.store.all("device", p["team"]) if d["id"] in p.get("devices", [])]
            ops = [o for o in self.store.all("operation", p["team"]) if o["deviceId"] in p.get("devices", []) and o["taskId"] in p.get("tasks", [])]
            return {"version": "0.3.0", "mode": "simulation" if self.demo else "hardware", "policy": self.policy, "principal": {"id": p["id"], "role": p["role"], "tasks": p.get("tasks", [])},
                    "devices": devices, "operations": sorted(ops, key=lambda o: o["createdAt"], reverse=True)[:200],
                    "capabilities": MATRIX["capabilities"], "tools": self.tools(p)}

    def register(self, p, body):
        self.role(p, "executor")
        require(body.get("platform") == p.get("platform"), "PERMISSION_DENIED", "Executor platform is fixed by provisioning", 403)
        require(bool(body.get("simulated")) == self.demo, "PERMISSION_DENIED", "Simulator and hardware databases must be separate", 403)
        require(isinstance(body.get("devices"), list) and len(body["devices"]) <= 20, "UNSUPPORTED_PARAMETER", "Invalid device list")
        with self.store.transaction():
            occupied = self.store.db.execute("SELECT team FROM records WHERE kind='executor' AND id=?", (p["id"],)).fetchone()
            require(not occupied or occupied[0] == p["team"], "PERMISSION_DENIED", "Executor ID already belongs to another team", 403)
            executor = {"id": p["id"], "team": p["team"], "platform": p["platform"], "simulated": self.demo, "lastSeen": self.clock(),
                        "adapterVersion": str(body.get("adapterVersion", "unknown"))[:128], "sdkArtifactHash": str(body.get("sdkArtifactHash", "unknown"))[:128], "sdkVersion": str(body.get("sdkVersion", "unknown"))[:128]}
            self.store.put("executor", executor)
            for incoming in body["devices"]:
                device_id = incoming.get("deviceId")
                require(device_id in p.get("devices", []), "PERMISSION_DENIED", "Cannot claim unprovisioned device", 403)
                occupied = self.store.db.execute("SELECT team FROM records WHERE kind='device' AND id=?", (device_id,)).fetchone()
                require(not occupied or occupied[0] == p["team"], "PERMISSION_DENIED", "Device ID already belongs to another team", 403)
                require(incoming.get("model") in ("T8171", "T8214"), "MODEL_NOT_APPLICABLE", "Unknown model")
                old = next((d for d in self.store.all("device", p["team"]) if d["id"] == device_id), {})
                require(not old or old["executorId"] == p["id"], "RESOURCE_BUSY", "Explicit device reassignment is required")
                routes = incoming.get("routes", {})
                require(isinstance(routes, dict) and not routes.keys() - TOOLS.keys(), "UNSUPPORTED_PARAMETER", "Unknown routes")
                for route in routes.values():
                    require(isinstance(route, dict) and isinstance(route.get("sdkMapping"), str), "UNSUPPORTED_PARAMETER", "Route needs SDK mapping")
                    require(len(route["sdkMapping"]) < 256, "UNSUPPORTED_PARAMETER", "SDK mapping too long")
                revision_key = fingerprint({"model": incoming["model"], "platform": p["platform"], "hash": executor["sdkArtifactHash"], "sdkVersion": executor["sdkVersion"], "adapter": executor["adapterVersion"], "firmware": incoming.get("firmwareVersion"), "routes": routes, "fields": incoming.get("fields", {})})
                d = {"id": device_id, "deviceId": device_id, "team": p["team"], "model": incoming["model"], "label": str(incoming.get("label", device_id))[:128],
                     "executorId": p["id"], "executorPlatform": p["platform"], "simulated": self.demo,
                     "firmwareVersion": str(incoming.get("firmwareVersion", "unknown"))[:128], "sdkArtifactHash": executor["sdkArtifactHash"], "sdkVersion": executor["sdkVersion"],
                     "capabilityRevision": revision_key, "viewRevision": old.get("viewRevision", 0), "settingsRevision": old.get("settingsRevision", 0), "viewConfirmationRequired": old.get("viewConfirmationRequired", False),
                     "routes": routes, "fields": incoming.get("fields", {}), "privacy": incoming.get("privacy", "unknown"),
                     "officialIdentityReady": incoming.get("officialIdentityReady") is True, "lastSeen": self.clock(),
                     "hardwareValidation": "not_run", "connectivity": "simulated" if self.demo else incoming.get("connectivity", "unknown")}
                self.store.put("device", d)
            self.store.audit(p, "executor.register", p["id"])
            return executor

    def validate_hardware(self, p, body):
        self.role(p, "human")
        require(not self.demo, "UNSUPPORTED_PARAMETER", "Simulation cannot create hardware validation")
        d = self.device(p, body["deviceId"])
        require(body.get("tool") in d["routes"], "SDK_ENTRY_UNCONFIRMED", "Adapter has no such route")
        require(body.get("capabilityRevision") == d["capabilityRevision"], "STALE_REFERENCE", "Capability revision changed")
        require(body.get("status") in ("passed", "failed", "not_run"), "UNSUPPORTED_PARAMETER", "Invalid status")
        check({"type": "string", "minLength": 10, "maxLength": 2000}, body.get("evidence", ""), "evidence")
        with self.store.transaction():
            selected_variant = body.get("variant", "step" if body["tool"] == "camera_ptz_step" else "default")
            require(isinstance(selected_variant, str) and 0 < len(selected_variant) <= 128, "UNSUPPORTED_PARAMETER", "Invalid validation variant")
            if body["tool"] == "camera_ptz_step":
                require(selected_variant in d["routes"][body["tool"]].get("motionModes", ["step"]), "UNSUPPORTED_PARAMETER", "Movement variant not implemented")
            if body["tool"] == "device_settings_set":
                require(selected_variant in d['fields'] and d['fields'][selected_variant].get('writable'),
                        'UNSUPPORTED_PARAMETER', 'Validate one implemented settings field explicitly')
            item = {"id": fingerprint([d["id"], body["tool"], selected_variant, d["capabilityRevision"]]), "team": p["team"], "deviceId": d["id"], "tool": body["tool"], "variant": selected_variant, "validationScope": scope(d),
                    "capabilityRevision": d["capabilityRevision"], "status": body["status"], "evidence": body["evidence"], "reviewedBy": p["id"], "at": self.clock()}
            self.store.put("validation", item)
            self.store.audit(p, "hardware.validation", item["id"])
            return item

    def _gate(self, p, d, name, args, diagnostic=False):
        cap = TOOLS[name]["capabilities"][0]
        if name == "device_settings_set":
            require(args["field"] in FIELDS, "UNSUPPORTED_PARAMETER", "Field is not allowed in generic settings")
            cap, schema = FIELDS[args["field"]]
            check(schema, args["value"], "value")
            registered = d["fields"].get(args["field"])
            require(registered and registered.get("writable"), "CAPABILITY_NOT_READY", "Field not currently writable")
            check(registered["schema"], args["value"], "value")
            require(args["expectedSettingsRevision"] == d["settingsRevision"], "STALE_REFERENCE", "Settings changed")
        marker = support(cap, d["executorPlatform"], d["model"])
        require(marker != "X", "MODEL_NOT_APPLICABLE", "This model does not support this capability")
        require(marker != "B", "PATH_BLOCKED", "Current official SDK route is blocked")
        require(marker != "U", "SDK_ENTRY_UNCONFIRMED", "No confirmed SDK entry")
        require(marker != "C" or diagnostic, "NOT_VALIDATED", "Candidate capability requires human diagnostic mode")
        route = d["routes"].get(name)
        require(route is not None, "SDK_ENTRY_UNCONFIRMED", "Executor has no implemented route for this tool")
        require(route.get("ready") is True, "CAPABILITY_NOT_READY", "Adapter route is not ready")
        if name == "camera_ptz_step":
            motion = args.get("motionMode", "step")
            require((motion == "continuous") == ("durationMs" in args), "UNSUPPORTED_PARAMETER", "Step has no duration; continuous requires durationMs")
            require(motion in route.get("motionModes", ["step"]), "CAPABILITY_NOT_READY", "Movement variant not implemented by this executor")
            if motion == "continuous":
                require(args["durationMs"] <= route.get("maxContinuousMs", 0), "UNSUPPORTED_PARAMETER", "Duration exceeds executor policy")
        executor = self.store.get("executor", d["executorId"])
        require(self.clock() - executor["lastSeen"] < 30, "EXECUTOR_UNAVAILABLE", "Executor heartbeat expired")
        require(d["officialIdentityReady"] or self.demo, "CAPABILITY_NOT_READY", "Official SDK identity unavailable")
        if not self.demo and not diagnostic:
            validations = self.store.all("validation", d["team"])
            require(any(v["deviceId"] == d["id"] and v["tool"] == name and v.get("variant", "default") == variant(name, args) and v["capabilityRevision"] == d["capabilityRevision"] and v["status"] == "passed" for v in validations), "NOT_VALIDATED", "This exact adapter/device revision and variant is not hardware validated")
        # Stops are handled independently and are never suppressed by this server privacy gate.
        if name not in ("device_state_get", "device_settings_get", "camera_events_query", "camera_event_get", "camera_evidence_get", "camera_evidence_download", "camera_presets_list", "doorbell_replies_list"):
            require(d["privacy"] == "off", "PRIVACY_BLOCKED", "Privacy is on or unknown")
        if "expectedViewRevision" in args:
            require(args["expectedViewRevision"] == d["viewRevision"], "STALE_REFERENCE", "View changed")
        ref_keys = {"referenceObservationId": "observation", "presetRef": "preset", "replyRef": "reply", "channelRef": "light", "modeRef": "mode", "optionRef": "option", "microphoneSessionRef": "microphone"}
        refs = {}
        for key, kind in ref_keys.items():
            if key in args:
                ref = self.record(p, "ref", args[key])
                require(ref["kind"] == kind and ref["deviceId"] == d["id"] and ref["validUntil"] > self.clock(), "STALE_REFERENCE", "Reference expired or belongs to a different route/device")
                require(ref.get("capabilityRevision") == d["capabilityRevision"], "STALE_REFERENCE", "Reference capability revision changed")
                if kind == "observation":
                    require(ref["viewRevision"] == d["viewRevision"], "STALE_REFERENCE", "Observation is from an earlier view")
                if kind == "reply":
                    require(ref.get("ready") is True, "CAPABILITY_NOT_READY", "Reply not prepared on this device")
                if kind in ("option", "mode", "light"):
                    require(name in ref.get("allowedTools", []), "UNSUPPORTED_PARAMETER", "Option belongs to a different setting route")
                refs[key] = ref
        if name == "camera_record_clip":
            policy = args["audioPolicy"]
            require(policy in route.get("audioPolicies", []), "UNSUPPORTED_PARAMETER", "Audio capture policy is not guaranteed by this adapter")
        if name == "camera_events_query" and "from" in args and "to" in args:
            require(args["from"] <= args["to"], "UNSUPPORTED_PARAMETER", "Invalid time range")
        return refs

    def invoke(self, p, name, args, context):
        self.role(p, "agent", "human")
        require(name in TOOLS and name in p.get("tools", TOOLS), "PERMISSION_DENIED", "Tool not granted", 403)
        check(TOOLS[name]["inputSchema"], args)
        check({"type": "object", "additionalProperties": False, "properties": {"taskId": {"type": "string", "minLength": 1, "maxLength": 256}, "idempotencyKey": {"type": "string", "minLength": 1, "maxLength": 128}, "requestedPlatform": {"type": "string", "enum": ["Android", "iOS", "Web"]}, "diagnostic": {"type": "boolean"}}, "required": ["taskId", "idempotencyKey", "requestedPlatform"]}, context, "context")
        require(context["taskId"] in p.get("tasks", []), "PERMISSION_DENIED", "Task not granted", 403)
        diagnostic = context.get("diagnostic", False)
        if diagnostic:
            self.role(p, "human")
        with self.store.transaction():
            self._expire(p["team"])
            if name == "devices_list":
                return {"devices": self.snapshot(p)["devices"], "source": "executor_registry", "refreshedAt": self.clock()}
            if name == "device_inspect":
                d = self.device(p, args["deviceId"])
                return {"device": d, "capabilities": [{"id": c["id"], "label": c["label"], "staticSupport": c["platforms"][d["executorPlatform"]][d["model"]], "hardwareValidation": "not_run"} for c in MATRIX["capabilities"]], "validations": [v for v in self.store.all("validation", p["team"]) if v["deviceId"] == d["id"]], "referenceBaselines": reference_baselines(d)}
            if name == "operation_get":
                return self.record(p, "operation", args["operationId"])
            if name in ("camera_stop", "camera_talk_stop", "operation_cancel"):
                return self._stop(p, args["operationId"], name)
            # References are looked up in the service; client strings cannot become SDK URLs/paths.
            resolved = {}
            for key, kind in (("eventRef", "event"), ("mediaRef", "media"), ("subscriptionId", "subscription")):
                if key in args:
                    ref = self.record(p, "ref", args[key])
                    require(ref["kind"] == kind and ref["validUntil"] > self.clock(), "STALE_REFERENCE", "Reference expired")
                    resolved[key] = ref
                    device_id = ref["deviceId"]
            if name == "camera_evidence_get" and resolved["mediaRef"].get("source") == "executor_upload":
                ref = resolved["mediaRef"]
                require(ref["taskId"] == context["taskId"], "PERMISSION_DENIED", "Media belongs to another task", 403)
                return {"media": ref, "readPath": "/v2/media/" + ref["id"], "authorization": "same scoped Bearer token", "source": "private_tool_store"}
            device_id = args.get("deviceId", locals().get("device_id"))
            d = self.device(p, device_id)
            digest = fingerprint({"name": name, "arguments": args, "context": context})
            key = fingerprint([p["team"], p["id"], context["taskId"], context["idempotencyKey"]])
            previous = [o for o in self.store.all("operation", p["team"]) if o["idempotencyRecord"] == key]
            if previous:
                require(previous[0]["requestHash"] == digest, "IDEMPOTENCY_CONFLICT", "Key already used for different parameters")
                return previous[0]
            resolved.update(self._gate(p, d, name, args, diagnostic))
            for ref in resolved.values():
                require(ref["taskId"] == context["taskId"], "PERMISSION_DENIED", "Reference belongs to another task", 403)
            now = self.clock()
            op = {"id": uid("op"), "team": p["team"], "principalId": p["id"], "deviceId": d["id"], "taskId": context["taskId"],
                  "tool": name, "arguments": deepcopy(args), "resolvedReferences": resolved, "requestHash": digest, "idempotencyRecord": key,
                  "requestedPlatform": context["requestedPlatform"], "executorPlatform": d["executorPlatform"], "executorId": d["executorId"],
                  "simulated": self.demo, "sdkUsed": False, "diagnostic": diagnostic, "capabilityRevision": d["capabilityRevision"],
                  "createdAt": now, "queueOrdinal": 1 + max((o.get("queueOrdinal", 0) for o in self.store.all("operation", p["team"])), default=0), "deadline": now + 120, "executionState": "awaitingApproval" if TOOLS[name]["control"] else "queued",
                  "dispatchState": "not_sent", "sdkResult": None, "physicalResult": "unverified", "evidenceRefs": [], "stopResult": None,
                  "sdkAccepted": None, "observedEffect": "unconfirmed", "artifactValidated": "unvalidated", "humanVerified": False, "validationScope": scope(d),
                  "viewRevision": d["viewRevision"], "settingsRevision": d["settingsRevision"], "control": TOOLS[name]["control"]}
            if d["executorPlatform"] != context["requestedPlatform"]:
                require(d["executorPlatform"] in p.get("allowedExecutorPlatforms", []), "PERMISSION_DENIED", "Cross-platform delegation is not granted", 403)
            # Existing direction-only grants must never silently cover continuous movement.
            if self.policy == "bounded" and op["control"] and not diagnostic and not (name == "camera_ptz_step" and args.get("motionMode") == "continuous"):
                for grant in self.store.all("grant", p["team"]):
                    if (grant["granteeId"] == p["id"] and grant["deviceId"] == d["id"] and grant["taskId"] == context["taskId"] and grant["tool"] == name
                            and not grant["revoked"] and grant["expiresAt"] > now and grant["remainingUses"] > 0
                            and all(args.get(key) in allowed for key, allowed in grant["allowedArguments"].items())):
                        grant["remainingUses"] -= 1
                        self.store.put("grant", grant)
                        op.update(executionState="queued", grantId=grant["id"], approvedBy=grant["approvedBy"], approvalKind="bounded_grant")
                        break
            self.store.put("operation", op)
            self.store.audit(p, "tool.request", op["id"])
            return op

    def grant(self, p, body):
        self.role(p, "human")
        require(self.policy == "bounded", "PERMISSION_DENIED", "Competition mode requires per-action confirmation", 403)
        d = self.device(p, body.get("deviceId"))
        name = body.get("tool")
        require(name in ("camera_ptz_step", "camera_goto_preset", "camera_set_night_vision", "camera_light_set", "doorbell_light_set", "camera_dual_mode_set", "camera_record_clip"), "UNSUPPORTED_PARAMETER", "Tool not eligible for bounded grants")
        task_id = body.get("taskId")
        require(task_id in p.get("tasks", []), "PERMISSION_DENIED", "Task outside human grant", 403)
        grantee = next((a for a in self.principals if a["id"] == body.get("granteeId") and a["role"] == "agent" and a["team"] == p["team"]), None)
        require(grantee is not None, "PERMISSION_DENIED", "Grantee must be a provisioned agent", 403)
        self.scoped(grantee, {"team": p["team"], "deviceId": d["id"], "taskId": task_id})
        allowed = body.get("allowedArguments", {})
        dynamic = {"deviceId", "referenceObservationId", "expectedViewRevision", "expectedSettingsRevision"}
        required = set(TOOLS[name]["inputSchema"]["required"]) - dynamic
        require(isinstance(allowed, dict) and set(allowed) == required, "UNSUPPORTED_PARAMETER", "Grant must constrain every non-reference argument")
        for key, options in allowed.items():
            require(isinstance(options, list) and 0 < len(options) <= 8, "UNSUPPORTED_PARAMETER", "Grant options must be a bounded nonempty list")
            for option in options:
                check(TOOLS[name]["inputSchema"]["properties"][key], option)
        check({"type": "integer", "minimum": 1, "maximum": 20}, body.get("maxUses"), "maxUses")
        check({"type": "integer", "minimum": 1, "maximum": 600}, body.get("duration"), "duration")
        with self.store.transaction():
            item = {"id": uid("grant"), "team": p["team"], "deviceId": d["id"], "taskId": task_id, "granteeId": grantee["id"], "tool": name,
                    "allowedArguments": allowed, "approvedBy": p["id"], "createdAt": self.clock(), "expiresAt": self.clock() + body["duration"],
                    "remainingUses": body["maxUses"], "revoked": False}
            self.store.put("grant", item)
            self.store.audit(p, "grant.created", item["id"])
            return item

    def revoke_grant(self, p, grant_id):
        self.role(p, "human")
        with self.store.transaction():
            grant = self.record(p, "grant", grant_id)
            grant["revoked"] = True
            self.store.put("grant", grant)
            for op in self.store.all("operation", p["team"]):
                if op.get("grantId") == grant_id:
                    self._stop(p, op["id"], "grant_revoke")
            self.store.audit(p, "grant.revoked", grant_id)
            return grant

    def approve(self, p, op_id, body):
        self.role(p, "human")
        with self.store.transaction():
            self._expire(p["team"])
            op = self.record(p, "operation", op_id)
            require(op["executionState"] == "awaitingApproval", "INVALID_STATE", "Operation is not awaiting approval")
            require(body.get("requestHash") == op["requestHash"], "STALE_REFERENCE", "Confirmation must match the exact request")
            require(body.get("decision") in ("approve", "reject"), "UNSUPPORTED_PARAMETER", "Explicit decision required")
            if body["decision"] == "approve":
                self._gate(p, self.device(p, op["deviceId"]), op["tool"], op["arguments"], op["diagnostic"])
            op.update(executionState="queued" if body["decision"] == "approve" else "cancelled", approvedBy=p["id"], approvedAt=self.clock())
            self.store.put("operation", op)
            self.store.audit(p, "operation." + body["decision"], op_id)
            return op

    def _stop(self, p, op_id, source):
        op = self.record(p, "operation", op_id)
        if source == "camera_talk_stop":
            require(op["tool"] == "camera_talk_start", "UNSUPPORTED_PARAMETER", "Not a talk operation")
        if op["executionState"] in ("queued", "awaitingApproval"):
            op.update(executionState="cancelled", stopResult={"state": "not_dispatched"})
        elif op["executionState"] in ("executing", "verifying", "unknown"):
            op.update(stopRequested=True, stopResult={"state": "requested", "physicalEffect": "unverified"})
        self.store.put("operation", op)
        self.store.audit(p, "operation.stop_requested", op_id)
        return op

    def claim(self, p, allow_new=True):
        self.role(p, "executor")
        with self.store.transaction():
            ex = self.store.get("executor", p["id"])
            ex["lastSeen"] = self.clock()
            self.store.put("executor", ex)
            self._expire(p["team"])
            ops = self.store.all("operation", p["team"])
            # Stops have priority and are not blocked by privacy/validation checks.
            for op in ops:
                if op["executorId"] == p["id"] and op.get("stopRequested") and not op.get("stopDispatched"):
                    op["stopDispatched"] = True
                    self.store.put("operation", op)
                    return {"command": "stop", "operation": op}
            if not allow_new:
                return {"command": None}
            busy = {o["deviceId"] for o in ops if o["executionState"] in ("executing", "verifying", "unknown") and not o.get("leaseReleasedByHuman")}
            for op in sorted(ops, key=lambda o: (o["createdAt"], o.get("queueOrdinal", 0))):
                if op["executorId"] != p["id"] or op["executionState"] != "queued" or op["deviceId"] in busy:
                    continue
                d = self.device(p, op["deviceId"])
                requester = next((v for v in self.principals if v["id"] == op["principalId"] and v["team"] == op["team"]), None)
                try:
                    require(requester is not None, "PERMISSION_DENIED", "Requester was revoked")
                    self.scoped(requester, op)
                    require(op["tool"] in requester.get("tools", TOOLS), "PERMISSION_DENIED", "Tool grant was revoked")
                    if op.get("grantId"):
                        grant = self.store.get("grant", op["grantId"])
                        require(not grant["revoked"] and grant["expiresAt"] > self.clock(), "PERMISSION_DENIED", "Bounded grant expired or revoked")
                    require(op["capabilityRevision"] == d["capabilityRevision"], "STALE_REFERENCE", "Adapter changed since request")
                    self._gate(requester, d, op["tool"], op["arguments"], op["diagnostic"])
                except ToolError as e:
                    op.update(executionState="failed", error={"code": e.code, "message": e.message})
                    self.store.put("operation", op)
                    continue
                op.update(executionState="executing", dispatchState="claimed", leaseToken=secrets.token_urlsafe(24), claimedAt=self.clock())
                self.store.put("operation", op)
                return {"command": "execute", "operation": op}
            return {"command": None}

    def finish(self, p, op_id, body):
        self.role(p, "executor")
        with self.store.transaction():
            op = self.record(p, "operation", op_id)
            require(op["executorId"] == p["id"] and body.get("leaseToken") == op.get("leaseToken") and op.get("leaseToken"), "PERMISSION_DENIED", "Executor lease mismatch", 403)
            received_hash = fingerprint(body)
            if received_hash in (op.get("resultHash"), op.get("executionReceiptHash"), op.get("stopReceiptHash")):
                return op  # Retry a lost HTTP result response without re-executing the physical command.
            require(body.get("simulated") is self.demo, "PERMISSION_DENIED", "Result provenance mismatch", 403)
            # An execution callback can arrive after the independent stop callback.
            # It must not overwrite cancellation, nor release an unresolved stop.
            command = body.get("command", "stop" if body.get("status") == "stopped" else "execute")
            if command == "execute" and op.get("stopRequested"):
                op["executionReceiptHash"] = fingerprint(body)
                op["executionReceipt"] = {"status": body.get("status"), "sdkUsed": body.get("sdkUsed") is True}
                if op["executionState"] not in ("completed", "failed", "cancelled", "unknown"):
                    op["executionState"] = "verifying" if self.clock() <= op["deadline"] else "unknown"
                self.store.put("operation", op)
                return op
            require(op["executionState"] in ("executing", "verifying", "unknown"), "INVALID_STATE", "Operation already settled")
            require(body.get("status") in ("acknowledged", "failed", "unknown", "stopped"), "UNSUPPORTED_PARAMETER", "Invalid result status")
            require(body.get("simulated") is self.demo, "PERMISSION_DENIED", "Result provenance mismatch", 403)
            require(body.get("sdkAccepted") is None or type(body.get("sdkAccepted")) is bool, "UNSUPPORTED_PARAMETER", "sdkAccepted must be boolean or null")
            if op["tool"] == "camera_observe" and body["status"] == "acknowledged" and not self.demo:
                try:
                    observations = [r for r in body.get("references", []) if r.get("kind") == "observation"]
                    require(len(observations) == 1, "STALE_FRAME", "A fresh observation requires one decoded frame")
                    check_frame(observations[0].get("frame"), op["deviceId"], self.clock() * 1000)
                    require(observations[0].get("dimensions") == observations[0]["frame"]["dimensions"], "STALE_FRAME", "Frame/image dimension mismatch")
                    require(bool(observations[0].get("mediaRef")), "STALE_FRAME", "Observation bytes are missing")
                except ToolError as e:
                    # Settle an unusable observation as failed; do not make the executor
                    # endlessly resend a rejected HTTP result, or publish the stale reference.
                    body = {**body, "status": "failed", "references": [], "error": {"code": e.code, "message": e.message}}
            if self.clock() > op["deadline"] and body["status"] != "stopped":
                op.update(executionState="unknown", lateResult=body.get("sdkResult"), physicalResult="unverified")
                return self.store.put("operation", op)
            if body["status"] == "stopped":
                require(op.get("stopRequested") is True, "INVALID_STATE", "Stop was not requested")
                op.update(executionState="cancelled", stopResult={"state": "acknowledged", "physicalEffect": "unverified"})
                op["stopReceiptHash"] = received_hash
            else:
                op["executionState"] = {"acknowledged": "completed", "failed": "failed", "unknown": "unknown"}[body["status"]]
                if op.get("stopDispatched") and body["status"] in ("failed", "unknown"):
                    op.update(executionState="unknown", stopResult={"state": "failed", "physicalEffect": "unverified"})
            op.update(dispatchState="returned", sdkResult=body.get("sdkResult"), sdkUsed=(not self.demo and body.get("sdkUsed") is True), physicalResult="unverified", completedAt=self.clock())
            op["sdkAccepted"] = None if not op["sdkUsed"] else body.get("sdkAccepted", True if body["status"] in ("acknowledged", "stopped") else None)
            # Executor ACKs and an official Demo report never create a human observation.
            op.update(observedEffect="unconfirmed", artifactValidated="unvalidated", humanVerified=False)
            if op["tool"] == "camera_ptz_step" and op["arguments"].get("motionMode") == "continuous" and body["status"] != "stopped" and (self.demo or op["sdkUsed"]):
                stop = body.get("stopResult") or {}
                stop_ack = stop.get("state") == "acknowledged"
                op["stopResult"] = {"state": "acknowledged" if stop_ack else "unknown", "sdkCode": stop.get("sdkCode"), "physicalEffect": "unverified", "source": "paired_stop"}
                if not stop_ack:
                    op.update(executionState="unknown", error={"code": "STOP_UNVERIFIED", "message": "Paired stop was not acknowledged; device lease retained"})
            if body.get("error"):
                op["error"] = {"code": str(body["error"].get("code", "SDK_ERROR"))[:128], "message": str(body["error"].get("message", "SDK error"))[:1000]}
            d = self.device(p, op["deviceId"])
            refs = []
            for incoming in (body.get("references", [])[:64] if body["status"] == "acknowledged" else []):
                # Vendor identifiers are opaque executor-only handles, never callable method names.
                require(incoming.get("kind") in ("observation", "event", "media", "preset", "reply", "light", "mode", "option", "subscription"), "UNSUPPORTED_PARAMETER", "Reference kind not accepted")
                ref = {key: value for key, value in incoming.items() if key in ("kind", "label", "vendorHandle", "sourceTimestamp", "sourceTimeKind", "dimensions", "sensor", "layout", "ready", "allowedTools", "source", "mimeType", "sha256", "size", "sessionId", "mediaRef", "frame")}
                if ref.get("mediaRef"):
                    media = self.record(p, "ref", ref["mediaRef"])
                    require(media["kind"] == "media" and media["operationId"] == op_id, "PERMISSION_DENIED", "Media belongs to another operation", 403)
                    op["artifactValidated"] = "integrity_checked"  # Not image/video full decode.
                ref.update(id=uid("ref"), team=op["team"], deviceId=op["deviceId"], taskId=op["taskId"], executorId=p["id"], simulated=self.demo,
                           receivedAt=self.clock(), validUntil=self.clock() + (op["arguments"].get("freshness", 15) if ref["kind"] == "observation" else 300),
                           viewRevision=d["viewRevision"], capabilityRevision=d["capabilityRevision"])
                if ref["kind"] == "observation":
                    require(op["tool"] == "camera_observe", "UNSUPPORTED_PARAMETER", "Observations must come from the observation tool")
                    ref.setdefault("sourceTimestamp", None)
                    ref.setdefault("sourceTimeKind", "unknown")
                    if not self.demo:
                        # Upload time cannot refresh the age of the source image.
                        ref["validUntil"] = min(ref["validUntil"], ref["frame"]["lastFrameAt"] / 1000 + op["arguments"].get("freshness", 15))
                        ref["roiStatus"] = "requires_confirmation" if d.get("viewConfirmationRequired") else "not_defined"
                self.store.put("ref", ref)
                refs.append(ref)
            op["result"] = {"data": body.get("data", {}), "references": refs}
            op["evidenceRefs"] = [r["id"] for r in refs if r["kind"] in ("observation", "media", "event")]
            if (body["status"] == "acknowledged" or op["sdkUsed"] and body["status"] in ("unknown", "stopped") or op["sdkAccepted"] is True):
                if op["tool"] in ("camera_ptz_step", "camera_goto_preset", "camera_dual_mode_set", "camera_ptz_mode_set", "camera_panorama_generate") and not op.get("viewInvalidated"):
                    d["viewRevision"] += 1
                    d["viewConfirmationRequired"] = True
                    op["viewInvalidated"] = True
                if op["tool"] in ("device_settings_set", "camera_set_night_vision", "camera_light_set", "doorbell_light_set"):
                    d["settingsRevision"] += 1
                self.store.put("device", d)
            op["resultHash"] = received_hash
            self.store.put("operation", op)
            self.store.audit(p, "operation.result", op_id)
            return op

    def review_result(self, p, body):
        """Human evidence review, independent of permission to run future operations."""
        self.role(p, "human")
        require(not self.demo, "UNSUPPORTED_PARAMETER", "Simulation cannot create human hardware evidence")
        with self.store.transaction():
            op = self.record(p, "operation", body.get("operationId"))
            require(body.get("requestHash") == op["requestHash"], "STALE_REFERENCE", "Review must match this operation")
            require(op["dispatchState"] == "returned", "INVALID_STATE", "No executor result to review")
            effect = body.get("observedEffect")
            require(effect in ("confirmed", "not_observed", "failed", "unconfirmed", "not_applicable"), "UNSUPPORTED_PARAMETER", "Invalid observation outcome")
            artifact = body.get("artifactValidated", op["artifactValidated"])
            require(artifact in ("unvalidated", "integrity_checked", "decoded", "not_applicable"), "UNSUPPORTED_PARAMETER", "Invalid artifact outcome")
            require(artifact != "decoded" or bool(op["evidenceRefs"]), "UNSUPPORTED_PARAMETER", "No artifact references to review")
            check({"type": "string", "minLength": 10, "maxLength": 2000}, body.get("evidence", ""), "evidence")
            op.update(observedEffect=effect, artifactValidated=artifact, humanVerified=True,
                      humanReview={"reviewedBy": p["id"], "at": self.clock(), "evidence": body["evidence"], "validationScope": op["validationScope"]})
            # Keep execution state, UNKNOWN lease and capability authorization unchanged.
            self.store.put("operation", op)
            self.store.audit(p, "operation.evidence_review", op["id"])
            return op

    def register_media(self, p, body):
        self.role(p, "executor")
        require(not self.demo, "UNSUPPORTED_PARAMETER", "Simulator does not create real media")
        with self.store.transaction():
            op = self.record(p, "operation", body.get("operationId"))
            require(op["executorId"] == p["id"] and op.get("leaseToken") and body.get("leaseToken") == op["leaseToken"], "PERMISSION_DENIED", "Media lease mismatch", 403)
            require(op["executionState"] == "executing" and op["deadline"] > self.clock(), "INVALID_STATE", "No active media operation")
            require(op["tool"] in ("camera_observe", "camera_evidence_get", "camera_evidence_download"), "PERMISSION_DENIED", "Operation is not authorized for image ingestion", 403)
            mime = body.get("mimeType")
            require(mime in ("image/png", "image/jpeg"), "UNSUPPORTED_PARAMETER", "Only bounded JPEG/PNG images in this revision")
            try:
                binary = base64.b64decode(body["base64"], validate=True)
            except (ValueError, KeyError):
                raise ToolError("UNSUPPORTED_PARAMETER", "Invalid base64 image")
            require(0 < len(binary) <= 2 * 1024 * 1024, "UNSUPPORTED_PARAMETER", "Image exceeds 2 MiB limit")
            require(binary.startswith(b"\x89PNG\r\n\x1a\n") if mime == "image/png" else binary.startswith(b"\xff\xd8\xff"), "UNSUPPORTED_PARAMETER", "Image signature does not match MIME")
            digest = hashlib.sha256(binary).hexdigest()
            require(body.get("sha256") == digest, "INTEGRITY_ERROR", "Image hash mismatch")
            existing = [r for r in self.store.all("ref", p["team"]) if r.get("operationId") == op["id"] and r.get("sha256") == digest]
            if existing:
                return existing[0]
            require(sum(r.get("operationId") == op["id"] for r in self.store.all("ref", p["team"])) < 5, "RESOURCE_BUSY", "Per-operation media limit reached")
            ref = {"id": uid("media"), "kind": "media", "team": p["team"], "deviceId": op["deviceId"], "taskId": op["taskId"], "operationId": op["id"],
                   "executorId": p["id"], "simulated": False, "mimeType": mime, "size": len(binary), "sha256": digest, "receivedAt": self.clock(), "validUntil": self.clock() + 300,
                   "source": "executor_upload", "syncState": "local_only", "r2State": "not_configured"}
            self.media_root.mkdir(parents=True, exist_ok=True)
            (self.media_root / ref["id"]).write_bytes(binary)
            self.store.put("ref", ref)
            return ref

    def reconcile(self, p, body):
        self.role(p, "human")
        with self.store.transaction():
            op = self.record(p, "operation", body.get("operationId"))
            require(op["executionState"] == "unknown", "INVALID_STATE", "Only unknown operations can be manually reconciled")
            require(body.get("requestHash") == op["requestHash"] and body.get("decision") == "release_after_manual_check", "UNSUPPORTED_PARAMETER", "Explicit matching reconciliation required")
            check({"type": "string", "minLength": 10, "maxLength": 2000}, body.get("evidence", ""), "evidence")
            # Keep original UNKNOWN and physical unverified. A human releasing a blocked queue
            # is not rewritten into a successful physical execution or hardware validation.
            op.update(leaseReleasedByHuman=p["id"], leaseReleasedAt=self.clock(), reconciliationEvidence=body["evidence"])
            self.store.put("operation", op)
            self.store.audit(p, "operation.manual_reconciliation", op["id"])
            return op

    def read_media(self, p, media_id):
        with self.store.transaction():
            ref = self.record(p, "ref", media_id)
            require(ref["kind"] == "media" and ref["validUntil"] > self.clock(), "STALE_REFERENCE", "Media unavailable or expired")
            require(media_id.startswith("media_") and all(c in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in media_id), "UNSUPPORTED_PARAMETER", "Invalid media ID")
            path = self.media_root / media_id
            require(path.is_file(), "NOT_FOUND", "Media bytes not present", 404)
            binary = path.read_bytes()
            require(hashlib.sha256(binary).hexdigest() == ref["sha256"], "INTEGRITY_ERROR", "Stored image hash mismatch")
            return binary, ref["mimeType"]

    def public_operation(self, op):
        # Model/human readers never receive an executor capability token or raw vendor handle.
        result = deepcopy(op)
        for key in ("leaseToken", "resolvedReferences", "idempotencyRecord"):
            result.pop(key, None)
        if "result" in result:
            for ref in result["result"].get("references", []):
                ref.pop("vendorHandle", None)
        return result
