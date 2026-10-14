import { useEffect, useRef, useState } from "react";
import {
  api,
  APIError,
  type CaptureCommand,
  type Device,
  type MediaSession,
} from "./api";
import { type SDKFrame } from "./sdk";
import { FrameGate } from "./frame-gate.mjs";

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
async function base64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let s = "";
  for (let i = 0; i < bytes.length; i += 8192)
    s += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(s);
}

export function LiveView({
  device,
  integration,
  onClose,
  onStatus,
  registerStop,
}: {
  device: Device;
  integration: unknown;
  onClose: () => void;
  onStatus: (ready: boolean) => void;
  registerStop?: (stop: () => Promise<void>) => void;
}) {
  const { Provider, DeviceLiveLayout } = window.WebSDK;
  const [state, setState] = useState("正在连接官方媒体服务");
  const [error, setError] = useState("");
  const [leased, setLeased] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const stop = useRef(false);
  const statusRef = useRef(onStatus);
  statusRef.current = onStatus;

  useEffect(() => {
    let disposed = false,
      session: MediaSession | undefined,
      unsubscribe: (() => void) | undefined;
    let fallbackVideo: HTMLVideoElement | undefined,
      fallbackID: number | undefined;
    let fallbackBusy = false;
    const gate = new FrameGate();
    let finish!: () => void;
    const finished = new Promise<void>((resolve) => {
      finish = resolve;
    });
    const requests = new Map<
      string,
      { command: CaptureCommand; received: number }
    >();
    stop.current = false;
    registerStop?.(async () => {
      stop.current = true;
      setLeased(false);
      unsubscribe?.();
      statusRef.current(false);
      await finished;
      await wait(350); // official Provider defers transport cleanup
    });
    const fail = (message: string) => {
      if (!disposed) {
        stop.current = true;
        setError(message);
        statusRef.current(false);
      }
    };
    const onFrame = (frame: SDKFrame) => {
      if (!disposed && !stop.current) gate.accept(frame);
    };

    // Safari and browsers without MediaStreamTrackProcessor can sample an
    // actual presented video frame. No screenshot of the UI or cached image.
    const fallback = (): boolean => {
      const video = container.current?.querySelector("video");
      if (!video || !video.requestVideoFrameCallback) return false;
      fallbackVideo = video;
      const canvas = document.createElement("canvas");
      const draw = (_: number, metadata: VideoFrameCallbackMetadata) => {
        if (disposed || stop.current) return;
        if (!fallbackBusy && video.readyState >= 2 && video.videoWidth > 0) {
          fallbackBusy = true;
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          try {
            canvas.getContext("2d")!.drawImage(video, 0, 0);
            canvas.toBlob(
              (blob) => {
                fallbackBusy = false;
                if (blob)
                  onFrame({
                    blob,
                    width: canvas.width,
                    height: canvas.height,
                    timestamp: metadata.mediaTime * 1e6,
                    capturedAt: Date.now(),
                  });
              },
              "image/jpeg",
              0.8,
            );
          } catch {
            fallbackBusy = false;
            fail("此浏览器不能读取直播画面，请使用 Chrome/Edge 或 iOS App");
          }
        }
        fallbackID = video.requestVideoFrameCallback(draw);
      };
      fallbackID = video.requestVideoFrameCallback(draw);
      return true;
    };

    const start = async () => {
      try {
        session = await api.request<MediaSession>("/api/media-sessions", {
          deviceId: device.id,
          platform: "web",
        });
        if (disposed || stop.current) return;
        // Do not mount the auto-starting vendor player before obtaining the
        // shared iOS/Web capture lease.
        setLeased(true);
        const connectStarted = Date.now();
        while (!disposed && !stop.current) {
          if (!unsubscribe && !fallbackVideo) {
            try {
              unsubscribe = window.WebSDK.subscribeMediaChannelFrames(
                device.sn,
                onFrame,
                {
                  intervalMs: 350,
                  mimeType: "image/jpeg",
                  quality: 0.8,
                  onError: () => fail("直播帧订阅已中断，请停止并重新连接"),
                },
              );
            } catch {
              fallback();
            }
          }
          const f = gate.frame as
            | (SDKFrame & {
                sequence: number;
                localAt: number;
                sampledAt: number;
              })
            | null;
          const age = f ? Date.now() - f.localAt : null;
          const ready = age !== null && age < 3000;
          await api.request(
            `/api/media-sessions/${session.id}/heartbeat`,
            {
              state: ready ? "streaming" : "connecting",
              sequence: gate.sequence,
              frameAgeMs: age === null ? null : Math.min(age, 86400000),
            },
            session,
          );
          if (disposed || stop.current) break;
          statusRef.current(ready);
          setState(
            ready ? "实时视频 · 新画面可供 Agent 使用" : "等待有效视频帧",
          );
          if (!ready && Date.now() - connectStarted > 45000) {
            fail(
              "尚未取得有效新帧。请检查设备唤醒、账号权限和浏览器，再重新连接。",
            );
            break;
          }
          const commands = await api.request<CaptureCommand[]>(
            `/api/media-sessions/${session.id}/commands`,
            undefined,
            session,
          );
          if (disposed || stop.current) break;
          const active = new Set(commands.map((command) => command.requestId));
          for (const id of requests.keys())
            if (!active.has(id)) requests.delete(id);
          for (const command of commands)
            if (!requests.has(command.requestId))
              requests.set(command.requestId, {
                command,
                received: gate.sequence,
              });
          for (const [id, pending] of requests) {
            if (pending.command.deadline * 1000 <= Date.now()) {
              requests.delete(id);
              continue;
            }
            const next = gate.after(pending.command, pending.received) as
              | (SDKFrame & { sequence: number; sampledAt: number })
              | null;
            if (!next) continue;
            const imageBase64 = await base64(next.blob);
            if (disposed || stop.current) break;
            try {
              await api.request(
                `/api/media-sessions/${session.id}/frames`,
                {
                  requestId: id,
                  sequence: next.sequence,
                  imageBase64,
                  width: next.width,
                  height: next.height,
                  sampledAt: next.sampledAt,
                  channelId: "main",
                },
                session,
              );
            } catch (e) {
              // A cancelled Agent request need not tear down a healthy player.
              // A stale/invalid session will still fail its next heartbeat.
              if (!(e instanceof APIError) || e.status !== 409) throw e;
            }
            requests.delete(id);
          }
          await wait(500);
        }
      } catch (e) {
        fail(e instanceof Error ? e.message : "媒体会话未完成");
      } finally {
        if (!disposed) setLeased(false);
        unsubscribe?.();
        if (fallbackVideo && fallbackID !== undefined)
          fallbackVideo.cancelVideoFrameCallback(fallbackID);
        if (session) {
          try {
            await api.request(
              `/api/media-sessions/${session.id}/stop`,
              {},
              session,
            );
          } catch {
            // Heartbeats have stopped. Do not start the official workspace
            // until the server's 12-second capture lease has expired.
            await wait(13000);
          }
        }
        statusRef.current(false);
        finish();
      }
    };
    void start();
    const hidden = () => {
      if (document.hidden) onClose();
    };
    document.addEventListener("visibilitychange", hidden);
    return () => {
      disposed = true;
      stop.current = true;
      unsubscribe?.();
      if (fallbackVideo && fallbackID !== undefined)
        fallbackVideo.cancelVideoFrameCallback(fallbackID);
      document.removeEventListener("visibilitychange", hidden);
      statusRef.current(false);
    };
  }, [device.id, device.sn, integration]);

  return (
    <div className="live-stage" ref={container}>
      {!error && !leased && (
        <div className="stream-loading">正在建立采集会话…</div>
      )}
      {!error && leased && (
        <Provider
          config={{ stationSn: device.sn, integration }}
          loadingComponent={
            <div className="stream-loading">正在唤醒设备，等待首帧…</div>
          }
        >
          <DeviceLiveLayout
            deviceSn={device.sn}
            onError={() => {
              stop.current = true;
              setError("官方媒体连接已中断，请重新开流");
              onStatus(false);
            }}
          />
        </Provider>
      )}
      {error && (
        <div className="stream-loading error">
          <strong>画面暂不可用</strong>
          <p>{error}</p>
          <button onClick={onClose}>结束本次会话</button>
        </div>
      )}
      <div className="stream-footer">
        <span>
          <i className={error ? "dot gray" : "dot"} />
          {error ? "已停止" : state}
        </span>
        <button className="text-button" onClick={onClose}>
          停止直播
        </button>
      </div>
    </div>
  );
}
